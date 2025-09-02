"""Test the behavior of the plugin's rules."""
from __future__ import annotations

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
    remind

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
        'Ignored URL are still "the last seen".'
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
