"""Plugin's configuration"""
from __future__ import annotations

from sopel import privileges
from sopel.config import types


class UrlSection(types.StaticSection):
    """Plugin's configuration.

    These options should be accessible through ``bot.settings.url``.
    """
    enable_auto_title = types.BooleanAttribute(
        'enable_auto_title', default=True)
    """Enable auto-title (enabled by default)"""
    # TODO some validation rules maybe?
    exclude = types.ListAttribute('exclude')
    """A list of regular expressions to match URLs to ignore."""
    exclude_required_access = types.ChoiceAttribute(
        'exclude_required_access',
        choices=[level.name for level in privileges.AccessLevel],
        default='OP',
    )
    """Minimum channel access level required to edit ``exclude`` list."""
    exclusion_char = types.ValidatedAttribute('exclusion_char', default='!')
    """The exclusion character to prevent URL matching.

    This character (or string) which, when immediately preceding a URL, will
    stop that URL's title from being shown.
    """
    shorten_url_length = types.ValidatedAttribute(
        'shorten_url_length', int, default=0)
    """Size limit before shortening URLs with TinyURL.

    If greater than 0, the title fetcher will include a TinyURL version of
    links longer than this many characters.
    """
    enable_private_resolution = types.BooleanAttribute(
        'enable_private_resolution', default=False)
    """Allow all requests to private and loopback networks.

    If disabled (the default), obvious attempts to load pages from loopback and
    private IP addresses will be blocked. If this matters for your security you
    must use additional protections like a firewall and CSRF tokens, since an
    attacker can change which IP address a domain name refers to between when
    Sopel checks it and when the HTTP request is made.
    """
