# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to handle i18n arguments in goofy tests."""

from __future__ import print_function

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import translation
from cros.factory.utils import arg_utils


def I18nArg(name, help_msg, optional=False, default=None):
  """Define an argument for i18n text.

  See docstring of ``ParseArgs`` for detail on what the argument accepts.

  Args:
    name: The name of the argument.
    help_msg: The help message of the argument.
    optional: Whether the argument is optional.
    default: The default value of the message.

  Returns:
    The ``arg_utils.Arg`` object.
  """
  return arg_utils.Arg(
      name, (basestring, dict), help_msg, optional=optional, default=default)


def ParseArg(test, name):
  """Parse arguments for i18n text.

  The argument should either be a string that would be passed to i18n._, or a
  dict looks like:

    {
      'en-US': 'Default English value',
      'zh-CN': 'Chinese Translate'
    }

  The key 'en-US' is mandatory and would be used for locales that don't have
  value specified.

  Args:
    test: The instance of pytest itself.
    name: The name of the argument, same as argument ``name`` passed to I18nArg.
  """
  # TODO(pihsun): The argument is always mandatory (or needs a default value)
  #   for now. Add support for optional=True if ever needed.
  # TODO(pihsun): When merge this back to arg_utils, we can make the call
  #   implicit for I18nArg, so people don't need to call this function manually.
  args = test.args
  arg = getattr(args, name, None)

  if arg is None:
    raise ValueError('{name} is mandatory.'.format(name=name))

  arg = translation.Translated(arg)
  setattr(args, name, arg)
