"""Test the behavior of the plugin's rules."""
from __future__ import annotations

import io
import typing

import pytest
from sopel.tests import rawlist

from sopel_url import backend, plugin

if typing.TYPE_CHECKING:
    from pytest import MonkeyPatch
    from sopel.bot import Sopel
    from sopel.config import Config
    from sopel.tests.factories import (BotFactory, ConfigFactory, IRCFactory,
                                       UserFactory)
    from sopel.tests.mocks import MockIRCServer, MockUser


TMP_CONFIG = """
[core]
owner = testnick
nick = TestBot
enable =
    coretasks
    url

[url]
enable_auto_title = true
"""


@pytest.fixture
def tmpconfig(configfactory: ConfigFactory) -> Config:
    return configfactory('test.cfg', TMP_CONFIG)


@pytest.fixture
def mockbot(tmpconfig: Config, botfactory: BotFactory) -> Sopel:
    return botfactory.preloaded(tmpconfig, preloads=['url'])


@pytest.fixture
def user(userfactory: UserFactory) -> MockUser:
    return userfactory('TestUser')


@pytest.fixture
def irc(
    mockbot: Sopel,
    user: MockUser,
    ircfactory: IRCFactory,
) -> MockIRCServer:
    server = ircfactory(mockbot)
    server.bot.backend.connected = True
    server.bot._connection_registered.set()  # nasty private-attribute access
    server.join(user, '#channel')
    server.bot.backend.clear_message_sent()
    return ircfactory(mockbot)


URL_MAPPING = {
    'https://example.com': backend.URLInfo(
        url='https://example.com',
        title='Example Website Title',
        hostname='example.com',
        tinyurl=None,
        ignored=False,
    ),
    'http://example.com': backend.URLInfo(
        url='http://example.com',
        title='Example Website Title (Insecure)',
        hostname='example.com',
        tinyurl=None,
        ignored=False,
    ),
    'https://test.example.com': backend.URLInfo(
        url='https://test.example.com',
        title='Example Website Title (Subdomain)',
        hostname='test.example.com',
        tinyurl='https://tinyurl.com/yck2cftj',
        ignored=False,
    ),
    'https://tinyurl.com/yck2cftj': backend.URLInfo(
        url='https://test.example.com',
        title='Example Website Title (Subdomain)',
        hostname='test.example.com',
        tinyurl='https://tinyurl.com/yck2cftj',
        ignored=False,
    ),
}


URL_MAPPING_HTTP_IGNORED = {
    'https://example.com': backend.URLInfo(
        url='https://example.com',
        title='Example Website Title',
        hostname='example.com',
        tinyurl=None,
        ignored=False,
    ),
    'http://example.com': backend.URLInfo(
        url='http://example.com',
        title='Example Website Title (Insecure)',
        hostname='example.com',
        tinyurl=None,
        ignored=True,
    ),
    'https://test.example.com': backend.URLInfo(
        url='https://test.example.com',
        title='Example Website Title (Subdomain)',
        hostname='test.example.com',
        tinyurl='https://tinyurl.com/yck2cftj',
        ignored=False,
    ),
}


def test_configure(tmpconfig: Config, monkeypatch: MonkeyPatch):
    user_inputs = io.StringIO('\n'.join((
        'n',  # enable_auto_title
        r'https://example\.com', '', ''  # exclude
        '$',  # exclusion_char
        '79',  # shorten_url_length
        'y',  # enable_private_resolution
    )))
    monkeypatch.setattr('sys.stdin', user_inputs)
    plugin.configure(tmpconfig)

    assert 'url' in tmpconfig
    assert hasattr(tmpconfig.url, 'enable_auto_title')
    assert hasattr(tmpconfig.url, 'exclude')
    assert hasattr(tmpconfig.url, 'exclusion_char')
    assert hasattr(tmpconfig.url, 'shorten_url_length')
    assert hasattr(tmpconfig.url, 'enable_private_resolution')

    assert tmpconfig.url.enable_auto_title is False
    assert tmpconfig.url.exclude == [r'https://example\.com']
    assert tmpconfig.url.exclusion_char == '$'
    assert tmpconfig.url.shorten_url_length == 79
    assert tmpconfig.url.enable_private_resolution is True


def test_title_command(
    irc: MockIRCServer,
    user: MockUser,
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr(
        plugin,
        'process_urls',
        lambda bot, urls, requested=False: [
            URL_MAPPING[url]
            for url in urls
        ],
    )
    irc.say(user, '#channel', '.title https://example.com')
    assert len(irc.bot.backend.message_sent) == 1
    assert irc.bot.backend.message_sent == rawlist(
        "PRIVMSG #channel :TestUser: Example Website Title | example.com",
    )

    assert '#channel' in irc.bot.memory['last_seen_url']
    assert 'https://example.com' == irc.bot.memory['last_seen_url']['#channel']

    irc.say(user, '#channel', '.title http://example.com')
    assert len(irc.bot.backend.message_sent[1:]) == 1
    assert irc.bot.backend.message_sent[1:] == rawlist(
        "PRIVMSG #channel :TestUser: Example Website Title (Insecure) "
        "| example.com",
    )

    assert 'http://example.com' == irc.bot.memory['last_seen_url']['#channel']

    irc.say(user, '#channel', '.title https://test.example.com')
    assert len(irc.bot.backend.message_sent[2:]) == 1
    assert irc.bot.backend.message_sent[2:] == rawlist(
        "PRIVMSG #channel :TestUser: Example Website Title (Subdomain) "
        "| test.example.com ( https://tinyurl.com/yck2cftj )",
    )

    found = irc.bot.memory['last_seen_url']['#channel']
    assert 'https://test.example.com' == found


def test_title_command_ignored(
    irc: MockIRCServer,
    user: MockUser,
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr(
        plugin,
        'process_urls',
        lambda bot, urls, requested=False: [
            URL_MAPPING_HTTP_IGNORED[url]
            for url in urls
        ],
    )
    irc.say(user, '#channel', '.title https://example.com')
    assert len(irc.bot.backend.message_sent) == 1
    assert irc.bot.backend.message_sent == rawlist(
        "PRIVMSG #channel :TestUser: Example Website Title | example.com",
    )

    assert '#channel' in irc.bot.memory['last_seen_url']
    assert 'https://example.com' == irc.bot.memory['last_seen_url']['#channel']

    irc.say(user, '#channel', '.title http://example.com')
    assert len(irc.bot.backend.message_sent[1:]) == 0

    assert 'http://example.com' != irc.bot.memory['last_seen_url']['#channel']
    assert 'https://example.com' == irc.bot.memory['last_seen_url']['#channel']

    irc.say(user, '#channel', '.title https://test.example.com')
    assert len(irc.bot.backend.message_sent[1:]) == 1
    assert irc.bot.backend.message_sent[1:] == rawlist(
        "PRIVMSG #channel :TestUser: Example Website Title (Subdomain) "
        "| test.example.com ( https://tinyurl.com/yck2cftj )",
    )

    found = irc.bot.memory['last_seen_url']['#channel']
    assert 'https://test.example.com' == found


def test_title_command_no_args(
    irc: MockIRCServer,
    user: MockUser,
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr(
        plugin,
        'process_urls',
        lambda bot, urls, requested=False: [
            URL_MAPPING[url]
            for url in urls
        ],
    )
    irc.say(user, '#channel', '.title')
    assert len(irc.bot.backend.message_sent) == 0
    assert '#channel' not in irc.bot.memory['last_seen_url']

    irc.say(user, '#channel', '.title https://example.com')
    assert irc.bot.backend.message_sent == rawlist(
        "PRIVMSG #channel :TestUser: Example Website Title | example.com",
    )

    irc.say(user, '#channel', '.title')
    assert len(irc.bot.backend.message_sent[1:]) == 1
    assert irc.bot.backend.message_sent == rawlist(
        "PRIVMSG #channel :TestUser: Example Website Title | example.com",
        "PRIVMSG #channel :TestUser: Example Website Title | example.com",
    )


def test_title_command_multi_urls(
    irc: MockIRCServer,
    user: MockUser,
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr(
        plugin,
        'process_urls',
        lambda bot, urls, requested=False: [
            URL_MAPPING[url]
            for url in urls
        ],
    )
    urls = [
        'https://example.com',
        'http://example.com',
        'https://test.example.com',
    ]
    irc.say(user, '#channel', '.title %s' % ' '.join(urls))
    assert len(irc.bot.backend.message_sent) == 3
    assert irc.bot.backend.message_sent == rawlist(
        "PRIVMSG #channel :TestUser: Example Website Title | example.com",
        "PRIVMSG #channel :TestUser: Example Website Title (Insecure) "
        "| example.com",
        "PRIVMSG #channel :TestUser: Example Website Title (Subdomain) "
        "| test.example.com ( https://tinyurl.com/yck2cftj )",
    )

    assert '#channel' in irc.bot.memory['last_seen_url']
    found = irc.bot.memory['last_seen_url']['#channel']
    assert 'https://test.example.com' == found


def test_title_command_multi_url_ignored(
    irc: MockIRCServer,
    user: MockUser,
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr(
        plugin,
        'process_urls',
        lambda bot, urls, requested=False: [
            URL_MAPPING_HTTP_IGNORED[url]
            for url in urls
        ],
    )

    urls = [
        'https://example.com',
        'http://example.com',
        'https://test.example.com',
    ]
    message = '.title %s' % ' '.join(urls)
    irc.say(user, '#channel', message)
    assert len(irc.bot.backend.message_sent) == 2
    assert irc.bot.backend.message_sent == rawlist(
        "PRIVMSG #channel :TestUser: Example Website Title | example.com",
        "PRIVMSG #channel :TestUser: Example Website Title (Subdomain) "
        "| test.example.com ( https://tinyurl.com/yck2cftj )",
    )
    assert '#channel' in irc.bot.memory['last_seen_url']
    found = irc.bot.memory['last_seen_url']['#channel']
    assert 'https://test.example.com' == found


def test_title_command_fail_to_process_urls(
    irc: MockIRCServer,
    user: MockUser,
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr(
        plugin,
        'process_urls',
        lambda bot, urls, requested=False: [],
    )

    irc.say(user, '#channel', '.title https://example.com')
    assert len(irc.bot.backend.message_sent) == 1
    assert irc.bot.backend.message_sent == rawlist(
        "PRIVMSG #channel :TestUser: Sorry, fetching that title failed. "
        "Make sure the site is working."
    )
    assert '#channel' not in irc.bot.memory['last_seen_url']

    irc.say(
        user,
        '#channel',
        '.title https://example.com https://test.example.com',
    )
    assert len(irc.bot.backend.message_sent[1:]) == 1
    assert irc.bot.backend.message_sent[1:] == rawlist(
        "PRIVMSG #channel :TestUser: Sorry, "
        "I couldn't fetch titles for any of those."
    )
    assert '#channel' not in irc.bot.memory['last_seen_url']


def test_title_command_partial_fail_to_process_urls(
    irc: MockIRCServer,
    user: MockUser,
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr(
        plugin,
        'process_urls',
        lambda bot, urls, requested=False: [
            backend.URLInfo(
                url='https://example.com',
                title='Example Website Title',
                hostname='example.com',
                tinyurl=None,
                ignored=False,
            ),
        ],
    )

    irc.say(
        user,
        '#channel',
        '.title https://example.com https://test.example.com',
    )
    assert len(irc.bot.backend.message_sent) == 2
    assert irc.bot.backend.message_sent == rawlist(
        "PRIVMSG #channel :TestUser: Example Website Title | example.com",
        "PRIVMSG #channel :TestUser: I couldn't get all of the titles, "
        "but I fetched what I could!"
    )
    assert '#channel' in irc.bot.memory['last_seen_url']
    assert 'https://example.com' == irc.bot.memory['last_seen_url']['#channel']


def test_title_auto(
    irc: MockIRCServer,
    user: MockUser,
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr(
        plugin,
        'process_urls',
        lambda bot, urls, requested=False: [
            URL_MAPPING[url]
            for url in urls
        ],
    )
    irc.say(user, '#channel', 'Here is my URL https://example.com')
    assert len(irc.bot.backend.message_sent) == 1
    assert irc.bot.backend.message_sent == rawlist(
        "PRIVMSG #channel :[url] Example Website Title | example.com",
    )

    assert '#channel' in irc.bot.memory['last_seen_url']
    assert 'https://example.com' == irc.bot.memory['last_seen_url']['#channel']

    irc.say(user, '#channel', 'Here is my URL http://example.com (not safe!)')
    assert len(irc.bot.backend.message_sent[1:]) == 1
    assert irc.bot.backend.message_sent[1:] == rawlist(
        "PRIVMSG #channel :[url] Example Website Title (Insecure) "
        "| example.com",
    )

    assert 'http://example.com' == irc.bot.memory['last_seen_url']['#channel']

    irc.say(user, '#channel', 'Here is my (sub) URL https://test.example.com')
    assert len(irc.bot.backend.message_sent[2:]) == 1
    assert irc.bot.backend.message_sent[2:] == rawlist(
        "PRIVMSG #channel :[url] Example Website Title (Subdomain) "
        "| test.example.com ( https://tinyurl.com/yck2cftj )",
    )

    found = irc.bot.memory['last_seen_url']['#channel']
    assert 'https://test.example.com' == found


def test_title_auto_disabled_auto_title(
    irc: MockIRCServer,
    user: MockUser,
    monkeypatch: MonkeyPatch,
):
    # prevent auto title by configuration
    irc.bot.settings.url.enable_auto_title = False
    monkeypatch.setattr(
        plugin,
        'process_urls',
        lambda bot, urls, requested=False: [
            URL_MAPPING[url]
            for url in urls
        ],
    )
    irc.say(user, '#channel', 'Here is my URL https://example.com')
    assert len(irc.bot.backend.message_sent) == 0
    assert '#channel' not in irc.bot.memory['last_seen_url']

    irc.say(user, '#channel', 'Here is my URL http://example.com (not safe!)')
    assert len(irc.bot.backend.message_sent) == 0
    assert '#channel' not in irc.bot.memory['last_seen_url']

    irc.say(user, '#channel', 'Here is my (sub) URL https://test.example.com')
    assert len(irc.bot.backend.message_sent) == 0
    assert '#channel' not in irc.bot.memory['last_seen_url']


def test_title_auto_ignored_url(
    irc: MockIRCServer,
    user: MockUser,
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr(
        plugin,
        'process_urls',
        lambda bot, urls, requested=False: [
            URL_MAPPING_HTTP_IGNORED[url]
            for url in urls
        ],
    )
    irc.say(user, '#channel', 'Here is my URL https://example.com')
    assert len(irc.bot.backend.message_sent) == 1
    assert irc.bot.backend.message_sent == rawlist(
        "PRIVMSG #channel :[url] Example Website Title | example.com",
    )

    assert 'https://example.com' == irc.bot.memory['last_seen_url']['#channel']

    irc.say(user, '#channel', 'Here is my URL http://example.com (not safe!)')
    assert len(irc.bot.backend.message_sent[1:]) == 0

    found = irc.bot.memory['last_seen_url']['#channel']
    assert 'http://example.com' == found, (
        'Ignored URL are still "the last seen". Unlike the command...'
    )

    irc.say(user, '#channel', 'Here is my (sub) URL https://test.example.com')
    assert len(irc.bot.backend.message_sent[1:]) == 1
    assert irc.bot.backend.message_sent[1:] == rawlist(
        "PRIVMSG #channel :[url] Example Website Title (Subdomain) "
        "| test.example.com ( https://tinyurl.com/yck2cftj )",
    )

    found = irc.bot.memory['last_seen_url']['#channel']
    assert 'https://test.example.com' == found


def test_title_auto_prevent_bot_trigger(
    irc: MockIRCServer,
    user: MockUser,
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr(
        plugin,
        'process_urls',
        lambda bot, urls, requested=False: [
            URL_MAPPING[url]
            for url in urls
        ],
    )
    irc.say(
        user,
        '#channel',
        "Example Website Title (Subdomain) | test.example.com "
        "( https://tinyurl.com/yck2cftj )",
    )
    assert len(irc.bot.backend.message_sent) == 0

    found = irc.bot.memory['last_seen_url']['#channel']
    assert 'https://test.example.com' == found
