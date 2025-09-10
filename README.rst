=========
sopel-url
=========

This plugin allows the bot to fetch URLs from messages and to reply with each
URL's title from the HTML content, if possible. You can trigger that with the
``.title <url>`` command::

    [08:42] Exirel: .title https://sopel.chat
    [08:42] Sopel: xrl: Sopel - The Python IRC Bot - Sopel | sopel.chat

And if ``enable_auto_title`` is enabled, the plugin will react to URLs as if
the ``.title`` command was used::

    [08:42] Exirel: Read the doc at https://sopel.chat/docs
    [08:42] Sopel: [url] Sopel 8.0.4 documentation | sopel.chat


Install
=======

The recommended way to install this plugin is to use ``pip``::

    $ python -m pip install sopel-url

Note that this plugin requires Python 3.8+ and Sopel 8.0+. It won't work on
Python versions that are not supported by the version of Sopel you are using.


Configuration
=============

This plugin defines the ``[url]`` section of the configuration file, with the
following directives:

* ``enable_auto_title`` (yes/no): Enable (yes, the default) or disable (no)
  auto-title.
* ``exclude`` (list): A list of regular expressions for URLs for which the
  title should not be shown. For example ``https?://git\.io/.*``
* ``exclusion_char`` (default ``!``): A character (or string) which, when
  immediately preceding a URL, will stop the URL's title from being shown.
* ``shorten_url_length`` (int, default 0): If greater than 0, the title fetcher
  will include a TinyURL version of links longer than this many characters.
* ``enable_private_resolution`` (yes/no): Enable (yes) or disable (no, the
  default) requests to private and local network IP addresses.
