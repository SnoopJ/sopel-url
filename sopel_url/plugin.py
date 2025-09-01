"""Sopel URL Title Plugin"""
# Copyright 2010-2011, Michael Yanovich (yanovich.net) & Kenneth Sham
# Copyright 2012-2013, Elsie Powell
# Copyright 2013, Lior Ramati <firerogue517@gmail.com>
# Copyright 2014, Elad Alfassa <elad@fedoraproject.org>
# Copyright 2025, Florian Strzelecki <florian.strzelecki@gmail.com>
# Licensed under the Eiffel Forum License 2.
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from sopel import plugin, privileges, tools

from .backend import process_urls
from .config import UrlSection

if TYPE_CHECKING:
    from sopel.bot import Sopel, SopelWrapper
    from sopel.config import Config
    from sopel.trigger import Trigger


LOGGER = logging.getLogger(__name__)


def configure(config: Config) -> None:
    """Configuration hook for sopel's configuration wizard.'"""
    config.define_section('url', UrlSection)
    config.url.configure_setting(
        'enable_auto_title',
        'Enable auto-title?'
    )
    config.url.configure_setting(
        'exclude',
        'Enter regular expressions for each URL you would like to exclude.'
    )
    config.url.configure_setting(
        'exclusion_char',
        'Enter a character which can be prefixed to suppress URL titling'
    )
    config.url.configure_setting(
        'shorten_url_length',
        'Enter how many characters a URL should be before the bot puts a'
        ' shorter version of the URL in the title as a TinyURL link'
        ' (0 to disable)'
    )
    config.url.configure_setting(
        'enable_private_resolution',
        'Allow all requests to private (local network) IP addresses?'
    )


def setup(bot: Sopel) -> None:
    """Plugin setup hook."""
    bot.settings.define_section('url', UrlSection)

    if bot.settings.url.exclude:
        regexes = [re.compile(s) for s in bot.config.url.exclude]
    else:
        regexes = []

    # We're keeping these in their own list, rather than putting then in the
    # callbacks list because 1, it's easier to deal with plugins that are still
    # using this list, and not the newer callbacks list and 2, having a lambda
    # just to pass is kinda ugly.
    if 'url_exclude' not in bot.memory:
        bot.memory['url_exclude'] = regexes
    else:
        exclude = bot.memory['url_exclude']
        if regexes:
            exclude.extend(regexes)
        bot.memory['url_exclude'] = exclude

    # Ensure last_seen_url is in memory
    if 'last_seen_url' not in bot.memory:
        bot.memory['last_seen_url'] = bot.make_identifier_memory()

    # Initialize shortened_urls as a dict if it doesn't exist.
    if 'shortened_urls' not in bot.memory:
        bot.memory['shortened_urls'] = tools.SopelMemory()


def shutdown(bot: Sopel) -> None:
    """Plugin's shutdown hook.

    Unset ``bot.memory['url_exclude']`` and `bot.memory['last_seen_url']`, but
    not `bot.memory['shortened_urls']`. Clearing ``shortened_urls`` will
    increase API calls. Leaving it in memory should not lead to unexpected
    behavior.
    """
    for key in ['url_exclude', 'last_seen_url']:
        try:
            del bot.memory[key]
        except KeyError:
            pass


def _user_can_change_excludes(bot: SopelWrapper, trigger: Trigger) -> bool:
    if trigger.admin:
        return True

    required_access = bot.config.url.exclude_required_access
    channel = bot.channels[trigger.sender]
    user_access = channel.privileges[trigger.nick]

    if user_access >= getattr(privileges.AccessLevel, required_access):
        return True

    return False


@plugin.command('urlexclude', 'urlpexclude', 'urlban', 'urlpban')
@plugin.example('.urlpexclude example\\.com/\\w+', user_help=True)
@plugin.example('.urlexclude example.com/path', user_help=True)
@plugin.output_prefix('[url] ')
def url_ban(bot: SopelWrapper, trigger: Trigger) -> None:
    """Exclude a URL from auto title.

    Use ``urlpexclude`` to exclude a pattern instead of a URL.
    """
    url = trigger.group(2)

    if not url:
        bot.reply('This command requires a URL to exclude.')
        return

    if not _user_can_change_excludes(bot, trigger):
        bot.reply(
            'Only admins and channel members with %s access or higher may '
            'modify URL excludes.' % bot.config.url.exclude_required_access)
        return

    if trigger.group(1) in ['urlpexclude', 'urlpban']:
        # validate regex pattern
        try:
            re.compile(url)
        except re.error as err:
            bot.reply('Invalid regex pattern: %s' % err)
            return
    else:
        # escape the URL to ensure a valid pattern
        url = re.escape(url)

    patterns = bot.settings.url.exclude

    if url in patterns:
        bot.reply('This URL is already excluded from auto title.')
        return

    # update settings
    patterns.append(url)
    bot.settings.url.exclude = patterns  # set the config option
    bot.settings.save()
    LOGGER.info('%s excluded the URL pattern "%s"', trigger.nick, url)

    # re-compile
    bot.memory['url_exclude'] = [re.compile(s) for s in patterns]

    # tell the user
    bot.reply('This URL is now excluded from auto title.')


@plugin.command('urlallow', 'urlpallow', 'urlunban', 'urlpunban')
@plugin.example('.urlpallow example\\.com/\\w+', user_help=True)
@plugin.example('.urlallow example.com/path', user_help=True)
@plugin.output_prefix('[url] ')
def url_unban(bot: SopelWrapper, trigger: Trigger) -> None:
    """Allow a URL for auto title.

    Use ``urlpallow`` to allow a pattern instead of a URL.
    """
    url = trigger.group(2)

    if not url:
        bot.reply('This command requires a URL to allow.')
        return

    if not _user_can_change_excludes(bot, trigger):
        bot.reply(
            'Only admins and channel members with %s access or higher may '
            'modify URL excludes.' % bot.config.url.exclude_required_access)
        return

    if trigger.group(1) in ['urlpallow', 'urlpunban']:
        # validate regex pattern
        try:
            re.compile(url)
        except re.error as err:
            bot.reply('Invalid regex pattern: %s' % err)
            return
    else:
        # escape the URL to ensure a valid pattern
        url = re.escape(url)

    patterns = bot.settings.url.exclude

    if url not in patterns:
        bot.reply('This URL was not excluded from auto title.')
        return

    # update settings
    patterns.remove(url)
    bot.settings.url.exclude = patterns  # set the config option
    bot.settings.save()
    LOGGER.info('%s allowed the URL pattern "%s"', trigger.nick, url)

    # re-compile
    bot.memory['url_exclude'] = [re.compile(s) for s in patterns]

    # tell the user
    bot.reply('This URL is not excluded from auto title anymore.')


@plugin.command('title')
@plugin.example('.title https://www.google.com', user_help=True)
@plugin.output_prefix('[url] ')
def title_command(bot: SopelWrapper, trigger: Trigger) -> None:
    """
    Show the title or URL information for the given URL, or the last URL seen
    in this channel.
    """
    result_count = 0

    if not trigger.group(2):
        if trigger.sender not in bot.memory['last_seen_url']:
            return
        urls = [bot.memory["last_seen_url"][trigger.sender]]
    else:
        # needs to be a list so len() can be checked later
        urls = list(tools.web.search_urls(trigger))

    for url, title, domain, tinyurl, ignored in process_urls(
        bot, urls, requested=True
    ):
        if ignored:
            result_count += 1
            continue
        message = "%s | %s" % (title, domain)
        if tinyurl:
            message += ' ( %s )' % tinyurl
        bot.reply(message)
        bot.memory['last_seen_url'][trigger.sender] = url
        result_count += 1

    expected_count = len(urls)
    if result_count < expected_count:
        if expected_count == 1:
            bot.reply("Sorry, fetching that title failed. "
                      "Make sure the site is working.")
        elif result_count == 0:
            bot.reply("Sorry, I couldn't fetch titles for any of those.")
        else:
            bot.reply("I couldn't get all of the titles, "
                      "but I fetched what I could!")


@plugin.rule(r'(?u).*(https?://\S+).*')
@plugin.output_prefix('[url] ')
def title_auto(bot: SopelWrapper, trigger: Trigger) -> None:
    """
    Automatically show titles for URLs. For shortened URLs/redirects, find
    where the URL redirects to and show the title for that.

    .. note::

        URLs that match (before redirection) any other registered callbacks
        will *not* have their titles shown.

    """
    # Enabled or disabled by feature flag
    if not bot.settings.url.enable_auto_title:
        return

    # Avoid fetching links from another command
    if re.match(bot.settings.core.prefix + r'\S+', trigger):
        return

    urls = tools.web.search_urls(
        trigger, exclusion_char=bot.settings.url.exclusion_char, clean=True)

    processed_urls = process_urls(bot, urls)
    for url, title, domain, tinyurl, ignored in processed_urls:
        if not ignored:
            message = '%s | %s' % (title, domain)
            if tinyurl:
                message += ' ( %s )' % tinyurl
            # Guard against responding to other instances of this bot.
            if message != trigger:
                bot.say(message)
        bot.memory["last_seen_url"][trigger.sender] = url
