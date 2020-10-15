# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to handle string operations for i18n text."""

import html
import logging
import string

from cros.factory.test.i18n import translation


class SafeFormatter(string.Formatter):
  """A string formatter that would put a placeholder for unknown key."""
  def __init__(self, placeholder='[?]'):
    super(SafeFormatter, self).__init__()
    self.placeholder = placeholder
    self.current_format_string = None

  def Warn(self, msg, *args):
    logging.warning('%r: ' + msg, self.current_format_string,
                    *args)

  def parse(self, format_string):
    self.current_format_string = format_string
    return super(SafeFormatter, self).parse(format_string)

  def get_value(self, key, args, kwargs):
    if isinstance(key, str):
      if not key:
        self.Warn('Using positional argument {} is not supported,'
                  ' use named argument instead.')
      if key not in kwargs:
        self.Warn('Key %s not found.', key)
      return kwargs.get(key, self.placeholder)

    self.Warn('Using positional argument {%d} is not recommended,'
              ' use named argument instead.', key)
    if 0 <= key < len(args):
      return args[key]
    return self.placeholder


_FORMATTER = SafeFormatter()


def StringFormat(_format_string, **kwargs):
  """Do format string on a translation dict.

  Args:
    _format_string: The format string used, can either be a string (would be
        passed to :func:`Translation`), or a translation dict.
    kwargs: arguments of format string.

  Example::

    StringFormat('{str1} {str2}', str1='String-1', str2=_('String-2'))

  If the text ``'{str1} {str2}'`` has translation ``'{str1}-{str2}'`` in zh-CN,
  the text ``'String-1'`` has translation ``'Text-1'`` in zh-CN, the text
  ``'String-2'`` has translation ``'Text-2'`` in zh-CN, then the returned
  translation dict would be::

    {
      'en-US': 'String-1 String-2',
      'zh-CN': 'String-1-Text-2'
    }
  """
  ret = {}
  _format_string = translation.Translated(_format_string)

  kwargs = {name: translation.Translated(val, translate=False)
            for name, val in kwargs.items()}
  for locale, format_str in _format_string.items():
    format_args = {name: val[locale] for name, val in kwargs.items()}
    ret[locale] = _FORMATTER.vformat(format_str, [], format_args)
  return ret


def _(_format_string, **kwargs):
  """Wrapper for i18n string processing.

  This function acts as :func:`Translation` when no kwargs is given, and as
  :func:`StringFormat` when kwargs is given. This function is also a marker
  for pygettext.
  """
  if not kwargs:
    return translation.Translation(_format_string)
  return StringFormat(_format_string, **kwargs)


def HTMLEscape(text):
  """HTML-escape all entries in a given translation dict.

  Args:
    text: The translation dict to be HTML-escaped.

  Returns:
    The new translation dict with all values HTML-escaped.
  """
  return {locale: html.escape(value, quote=False)
          for locale, value in text.items()}
