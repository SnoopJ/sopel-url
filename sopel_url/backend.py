"""Plugin's backend"""
from __future__ import annotations

import re
from email.message import EmailMessage
from ipaddress import ip_address
from socket import IPPROTO_TCP, getaddrinfo
from typing import TYPE_CHECKING, NamedTuple
from urllib.parse import urlparse

import requests
from sopel import tools
from urllib3.exceptions import LocationValueError  # type: ignore[import]

LOGGER = tools.get_logger('url')


if TYPE_CHECKING:
    from typing import Iterable

    from sopel.bot import SopelWrapper


USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/98.0.4758.102 Safari/537.36'
)
DEFAULT_HEADERS = {
    'User-Agent': USER_AGENT,
    'Accept': ', '.join((
        'text/html',
        'application/xhtml+xml',
        'application/xml;q=0.9',
        '*/*;q=0.8',
    )),
    'Accept-Language': 'en,en-US;q=0,5',
}
# These are used to clean up the title tag before actually parsing it. Not the
# world's best way to do this, but it'll do for now.
TITLE_TAG_DATA = re.compile('<(/?)title( [^>]+)?>', re.IGNORECASE)
QUOTED_TITLE = re.compile('[\'"]<title>[\'"]', re.IGNORECASE)
# This sets the maximum number of bytes that should be read in order to find
# the title. We don't want it too high, or a link to a big file/stream will
# just keep downloading until there's no more memory. 640k ought to be enough
# for anybody, but the modern web begs to differ.
MAX_BYTES = 655360 * 2


class URLInfo(NamedTuple):
    """Helper class for information about a URL handled by this plugin."""

    url: str

    title: str | None
    """The title associated with ``url``, if appropriate."""

    hostname: str | None
    """The hostname associated with ``url``, if appropriate."""

    tinyurl: str | None
    """A shortened form of ``url``, if appropriate."""

    ignored: bool
    """Whether or not this URL should be ignored.

    If a URL matches any registered callbacks or is explicitly excluded, then
    it should be ignored.
    """


def process_urls(
    bot: SopelWrapper,
    urls: list[str],
    requested: bool = False,
) -> Iterable[URLInfo]:
    """
    For each URL in the list, ensure it should be titled, and do so.

    :param bot: Sopel instance
    :param trigger: The trigger object for this event
    :param urls: The URLs detected in the triggering message
    :param requested: Whether the title was explicitly requested (vs automatic)

    Yields a tuple ``(url, title, hostname, tinyurl, ignored)`` for each URL.

    .. note:

        If a URL in ``urls`` has any registered callbacks, this function will
        NOT retrieve the title, and considers the URL as dispatched to those
        callbacks. In this case, only the ``url`` and ``ignored=True`` will be
        set; all other values will be ``None``.

    .. note:

        For titles explicitly requested by the user, ``exclusion_char`` and
        exclusions from the ``.urlban``/``.urlpban`` commands are skipped.

    .. versionchanged:: 8.0

        This function **does not** notify callbacks registered for URLs
        redirected to from URLs passed to this function. See #2432, #2230.

    """
    shorten_url_length = bot.settings.url.shorten_url_length
    for url in urls:
        # Exclude URLs that start with the exclusion char
        if not requested and url.startswith(bot.settings.url.exclusion_char):
            continue

        if check_callbacks(bot, url, use_excludes=not requested):
            # URL matches a callback OR is excluded, ignore
            yield URLInfo(url, None, None, None, True)
            continue

        # Call the URL to get a title, if possible
        unsafe_urls = [
            url
            for url, data in bot.memory.get("safety_cache", {}).items()
            if data.get("positives")
        ]
        title_results = find_title(
            url,
            allow_local=bot.config.url.enable_private_resolution,
            unsafe_urls=unsafe_urls,
            unsafe_domains=bot.memory.get("safety_cache_local", set()),
        )
        if not title_results:
            # No title found: don't handle this URL
            LOGGER.debug('No title found; ignoring URL: %s', url)
            continue
        title, final_hostname = title_results

        # If the URL is over bot.config.url.shorten_url_length, shorten the URL
        tinyurl = None
        if shorten_url_length and len(url) > shorten_url_length:
            tinyurl = get_or_create_shorturl(bot, url)

        yield URLInfo(url, title, final_hostname, tinyurl, False)


def check_callbacks(
    bot: SopelWrapper,
    url: str,
    use_excludes: bool = True,
) -> bool:
    """Check if ``url`` is excluded or matches any URL callback patterns.

    :param bot: Sopel instance
    :param url: URL to check
    :param use_excludes: Use or ignore the configured exclusion lists
    :return: True if ``url`` is excluded or matches any URL callback pattern

    This function looks at the ``bot.memory`` for ``url_exclude`` patterns and
    it returns ``True`` if any matches the given ``url``. Otherwise, it looks
    at the ``bot``'s URL callback patterns, and it returns ``True`` if any
    matches, ``False`` otherwise.

    .. seealso::

        The :attr:`UrlSection.exclude` parameter that defines the list of
        pattern stored in ``bot.memory['url_exclude']``.

    .. versionchanged:: 7.0

        This function **does not** trigger URL callbacks anymore when ``url``
        matches a pattern.

    """
    # Check if it matches the exclusion list first
    excluded = use_excludes and any(
        regex.search(url) for regex in bot.memory["url_exclude"]
    )
    return (
        excluded or
        # TODO: _url_callbacks is deprecated and will be removed in Sopel 9.0
        any(pattern.search(url) for pattern in bot._url_callbacks.keys()) or
        bot.rules.check_url_callback(bot, url)
    )


def find_title(
    url: str,
    verify: bool = True,
    allow_local: bool = False,
    unsafe_urls: Iterable[str] | None = None,
    unsafe_domains: Iterable[str] | None = None,
) -> tuple[str, str] | None:
    """Fetch the title for the given URL.

    :param verify: Whether to require a valid certificate when using https
    :param allow_local: Allow requests to non-global addresses (RFC1918, etc.)
    :param unsafe_urls: An iterable of URLs to consider malicious and to ignore
    :param unsafe_domains: An iterable of domains to consider malicious
                           and to ignore
    :return: A tuple of the (title, final_hostname) that were found, or None
    """
    original_url = url
    redirects_left = 5
    session = requests.Session()
    session.headers = dict(DEFAULT_HEADERS)
    unsafe_urls = unsafe_urls or []
    unsafe_domains = unsafe_domains or []

    while redirects_left > 0:
        redirects_left -= 1
        parsed_url = urlparse(url)
        if not parsed_url.hostname:
            return None

        # Avoid fetching known malicious links
        if url in unsafe_urls:
            LOGGER.debug("Ignoring unsafe URL: %r", url)
            return None
        if parsed_url.hostname.lower() in unsafe_domains:
            LOGGER.debug("Ignoring unsafe domain: %r", url)
            return None

        # Prevent private addresses from being queried
        try:
            # If link is to an IP
            ips = [ip_address(parsed_url.hostname)]
        except ValueError:  # Nope, hostname
            try:
                # getaddrinfo instead of dns.resolver so we use normal OS
                # name resolution, including hosts files.
                addr_info = getaddrinfo(
                    parsed_url.hostname,
                    443,
                    proto=IPPROTO_TCP,
                )
                ips = [ip_address(info[4][0]) for info in addr_info]
            except Exception as e:
                LOGGER.debug("Failed to get IPs for %r: %s", url, e)
                return None

        # is_global excludes RFC1918, loopback, link-local, and v6 equivalents
        if not allow_local and not all(ip.is_global for ip in ips):
            redirected_to_msg = ""
            if url != original_url:
                redirected_to_msg = " (redirected from %r)" % original_url
            LOGGER.debug(
                "Ignoring private URL %r%s which resolved to %s",
                url,
                redirected_to_msg,
                ", ".join([str(ip) for ip in ips]),
            )
            return None

        try:
            response = session.get(
                url,
                stream=True,
                verify=verify,
                allow_redirects=False,
            )
            if response.is_redirect:
                LOGGER.debug(
                    "URL %r redirected to %r",
                    url,
                    response.headers.get("Location"),
                )
                if "Location" not in response.headers:
                    return None
                url = response.headers["Location"]
                continue

            content_bytes = b''
            for chunk in response.iter_content(chunk_size=512):
                content_bytes += chunk
                if (
                    b"</title>" in content_bytes
                    or len(content_bytes) > MAX_BYTES
                ):
                    break

            encoding = None
            if "Content-Type" in response.headers:
                msg = EmailMessage()
                msg["Content-Type"] = response.headers["Content-Type"]
                encoding = msg.get_content_charset()
            content = content_bytes.decode(
                encoding or "utf-8",
                errors="ignore",
            )

            # Need to close the connection because we haven't read all the data
            response.close()
        except requests.exceptions.ConnectionError as e:
            LOGGER.debug("Unable to reach URL: %r: %s", url, e)
            return None
        except (
            requests.exceptions.InvalidURL,  # e.g. http:///
            UnicodeError,  # e.g. http://.example.com (urllib3<1.26)
            LocationValueError,  # e.g. http://.example.com (urllib3>=1.26)
        ):
            LOGGER.debug('Invalid URL: %s', url)
            return None
        break
    else:
        LOGGER.debug("Redirects exhausted for %r", original_url)
        return None

    # Some cleanup that I don't really grok, but was in the original, so
    # we'll keep it (with the compiled regexes made global) for now.
    content = TITLE_TAG_DATA.sub(r'<\1title>', content)
    content = QUOTED_TITLE.sub('', content)

    start = content.rfind('<title>')
    end = content.rfind('</title>')
    if start == -1 or end == -1:
        return None

    title = tools.web.decode(content[start + 7:end])
    title = title.strip()[:200]

    title = ' '.join(title.split())  # cleanly remove multiple spaces

    return (title, parsed_url.hostname)


def get_or_create_shorturl(bot: SopelWrapper, url: str) -> str | None:
    """Get or create a short URL for ``url``

    :param bot: Sopel instance
    :param url: URL to get or create a short URL for
    :return: A short URL

    It gets the short URL for ``url`` from the bot's memory if it exists.
    Otherwise, it creates a short URL (see :func:`get_tinyurl`), stores it
    into the bot's memory, then returns it.
    """
    # Check bot memory to see if the shortened URL is already in
    # memory
    if url in bot.memory['shortened_urls']:
        return bot.memory['shortened_urls'][url]

    tinyurl = get_tinyurl(url)
    bot.memory['shortened_urls'][url] = tinyurl
    return tinyurl


def get_tinyurl(url: str) -> str | None:
    """Returns a shortened tinyURL link of the URL"""
    base_url = "https://tinyurl.com/api-create.php"
    tinyurl = "%s?%s" % (base_url, tools.web.urlencode({'url': url}))
    try:
        res = requests.get(tinyurl)
        res.raise_for_status()
    except requests.exceptions.RequestException:
        return None
    # Replace text output with https instead of http to make the
    # result an HTTPS link.
    return res.text.replace("http://", "https://")
