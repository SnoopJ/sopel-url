"""Tests for Sopel's ``url`` plugin"""
from __future__ import annotations

import re

import pytest
from sopel import bot, plugins, trigger

from sopel_url.plugin import (_user_can_change_excludes, check_callbacks,
                              find_title)

TMP_CONFIG = """
[core]
owner = testnick
nick = TestBot
enable = coretasks
"""


INVALID_URLS = (
    "http://.example.com/",  # empty label
    "http://example..com/",  # empty label
    "http://?",  # no host
)
PRIVATE_URLS = (
    # "https://httpbin.org/redirect-to?url=http://127.0.0.1/",  # online
    "http://127.1.1.1/",
    "http://10.1.1.1/",
    "http://169.254.1.1/",
)

MOCK_MODULE_CONTENT = """
import re

from sopel import plugin

@plugin.url(re.escape('https://example.com/') + r'(.+)')
@plugin.label('handle_urls_https')
def url_callback_https(bot, trigger, match):
    pass

@plugin.url(re.escape('http://example.com/') + r'(.+)')
@plugin.label('handle_urls_http')
def url_callback_http(bot, trigger, match):
    pass
"""


@pytest.fixture
def mockplugin(tmpdir):
    root = tmpdir.mkdir('plugins')
    mod_file = root.join('testplugin.py')
    mod_file.write(MOCK_MODULE_CONTENT)
    return plugins.handlers.PyFilePlugin(mod_file.strpath)


@pytest.fixture
def mockbot(configfactory, mockplugin):
    tmpconfig = configfactory('test.cfg', TMP_CONFIG)
    url_plugin = plugins.handlers.PyModulePlugin('url', 'sopel.builtins')

    # setup the bot
    sopel = bot.Sopel(tmpconfig)
    url_plugin.load()
    url_plugin.setup(sopel)
    url_plugin.register(sopel)

    # register test plugin
    mockplugin.load()
    mockplugin.setup(sopel)
    mockplugin.register(sopel)

    # manually register URL Callback
    pattern = re.escape('https://help.example.com/') + r'(.+)'

    def callback(bot, trigger, match):
        pass

    sopel.register_url_callback(pattern, callback)
    return sopel


PRELOADED_CONFIG = """
[core]
owner = testnick
nick = TestBot
enable =
    coretasks
    url
"""


@pytest.fixture
def preloadedbot(configfactory, botfactory):
    tmpconfig = configfactory('preloaded.cfg', PRELOADED_CONFIG)
    return botfactory.preloaded(tmpconfig, ['url'])


@pytest.mark.parametrize("site", INVALID_URLS)
def test_find_title_invalid(site):
    # All local for invalid ones
    assert find_title(site) is None


@pytest.mark.parametrize("site", PRIVATE_URLS)
def test_find_title_private(site):
    assert find_title(site) is None


def test_check_callbacks(mockbot):
    """Test that check_callbacks works with both new & legacy URL callbacks."""
    assert check_callbacks(mockbot, 'https://example.com/test')
    assert check_callbacks(mockbot, 'http://example.com/test')
    assert check_callbacks(mockbot, 'https://help.example.com/test')
    assert not check_callbacks(mockbot, 'https://not.example.com/test')


def test_url_triggers_rules_and_auto_title(mockbot):
    line = ':Foo!foo@example.com PRIVMSG #sopel :https://not.example.com/test'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = mockbot.rules.get_triggered_rules(mockbot, pretrigger)

    assert len(results) == 1, 'Only one should match'
    result = results[0]
    assert isinstance(result[0], plugins.rules.Rule)
    assert result[0].get_rule_label() == 'title_auto'

    line = ':Foo!foo@example.com PRIVMSG #sopel :https://example.com/test'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = mockbot.rules.get_triggered_rules(mockbot, pretrigger)

    assert len(results) == 2, (
        'Two rules should match: title_auto and handle_urls_https')
    labels = sorted(result[0].get_rule_label() for result in results)
    expected = ['handle_urls_https', 'title_auto']
    assert labels == expected


@pytest.mark.parametrize('level, result', (
    ('NOTHING', False),
    ('VOICE', False),
    ('HALFOP', False),
    ('OP', True),
    ('ADMIN', True),
    ('OWNER', True),
))
def test_url_ban_privilege(
    preloadedbot,
    ircfactory,
    triggerfactory,
    level,
    result,
):
    """Make sure the urlban command privilege check functions correctly."""
    irc = ircfactory(preloadedbot)
    irc.channel_joined('#test', [
        'Unothing', 'Uvoice', 'Uhalfop', 'Uop', 'Uadmin', 'Uowner'])
    irc.mode_set('#test', '+vhoaq', [
        'Uvoice', 'Uhalfop', 'Uop', 'Uadmin', 'Uowner'])

    nick = f'U{level.title()}'
    user = level.lower()
    line = f':{nick}!{user}@example.com PRIVMSG #test :.urlban *'
    wrapper = triggerfactory.wrapper(preloadedbot, line)
    match = triggerfactory(preloadedbot, line)

    # parameter matrix assumes the default `exclude_required_access` config
    # value, which was 'OP' at the time of test creation
    assert _user_can_change_excludes(wrapper, match) == result
