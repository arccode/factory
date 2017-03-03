# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to handle string operations for i18n text."""

from __future__ import print_function

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import translation


def StringFormat(_format_string, **kwargs):
  """Do format string on a translation dict.

  Args:
    _format_string: The format string used, can either be a string (would be
        passed to _), or a translation dict.
    kwargs: arguments of format string.

  Example:
    StringFormat(_('{str1} {str2}'), str1='String-1', str2=_('String-2'))

    If the text '{str1} {str2}' has translation '{str1}-{str2}' in zh-CN,
       the text 'String-1' has translation 'Text-1' in zh-CN,
       the text 'String-2' has translation 'Text-2' in zh-CN,
    then the returned translation dict would be:
      {
        'en-US': 'String-1 String-2',
        'zh-CN': 'String 1-Text-2'
      }
  """
  ret = {}
  _format_string = translation.Translated(_format_string)
  kwargs = {name: translation.Translated(val, translate=False)
            for name, val in kwargs.iteritems()}
  for locale, format_str in _format_string.iteritems():
    format_args = {name: val[locale] for name, val in kwargs.iteritems()}
    ret[locale] = format_str.format(**format_args)
  return ret


def StringJoin(*strs):
  """Join several translation dicts / strings together.

  Args:
    strs: Strings / translation dicts to be joined together. Strings passed in
        would be used directly without translation.

  Example:
    >>> StringJoin('<div>', {'en-US': 'English', 'zh-CN': 'Chinese'}, '</div>')
    {'en-US': '<div>English</div>', 'zh-CN': '<div>Chinese</div>'}
  """
  strs = [translation.Translated(s, translate=False) for s in strs]
  return {
      locale: ''.join(s.get(locale) for s in strs)
      for locale in translation.LOCALES
  }
