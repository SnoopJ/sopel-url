"""Tests for ``sopel_url.backend``"""
from __future__ import annotations

import os
import re

import pytest
from sopel import bot, plugins

from sopel_url.backend import check_callbacks, find_title

TMP_CONFIG = """
[core]
owner = testnick
nick = TestBot
enable = coretasks
"""


@pytest.fixture
def mockplugin():
    filename = os.path.join(os.path.dirname(__file__), 'mockplugin.py')
    return plugins.handlers.PyFilePlugin(filename)


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
