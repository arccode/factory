# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to handle i18n arguments in goofy tests."""

from cros.factory.test.i18n import translation
from cros.factory.utils import arg_utils


# pylint: disable=protected-access
def I18nArg(name, help_msg, default=arg_utils._DEFAULT_NOT_SET):
  """Define an argument for i18n text.

  The argument should either be a string that would be passed to
  :func:`~cros.factory.test.i18n.Translation`, or a dict looks like::

    {
      'en-US': 'Default English value',
      'zh-CN': 'Chinese Translate'
    }

  The key ``'en-US'`` is mandatory and would be used for locales that don't
  have value specified.

  Args:
    name: The name of the argument.
    help_msg: The help message of the argument.
    default: The default value of the message.

  Returns:
    The ``arg_utils.Arg`` object.
  """
  return arg_utils.Arg(
      name, (str, dict), help_msg, default=default,
      _transform=lambda s: None if s is None else translation.Translated(s))
