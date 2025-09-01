"""Mock single file plugin for testing purpose."""
from __future__ import annotations

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
