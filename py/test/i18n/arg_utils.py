# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to handle i18n arguments in goofy tests."""

from __future__ import print_function
import logging

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import translation
from cros.factory.utils import arg_utils


def I18nArg(name, help_msg, optional=False, default=None,
            accept_tuple=False):
  """Define an argument for i18n text.

  See docstring of ``ParseArgs`` for detail on what the argument accepts.

  Args:
    name: The name of the argument.
    help_msg: The help message of the argument.
    optional: Whether the argument is optional.
    default: The default value of the message.
    accept_tuple: If true, also accept tuple of (en, zh) input.

  Returns:
    The ``arg_utils.Arg`` object.
  """
  # TODO(pihsun): accept_tuple argument is for backward compatibility, and
  #   should be removed when all tests / test_lists are migrated to the new
  #   format.
  return arg_utils.Arg(
      name, (basestring, dict, tuple) if accept_tuple else (basestring, dict),
      help_msg, optional=optional, default=default)


def BackwardCompatibleI18nArgs(name, help_msg, default=None):
  """Define arguments for i18n text in a backward compatible manner.

  This would also defines ``name``_en and ``name``_zh, so that the old argument
  format in test list would work.

  See docstring of ``ParseArg`` for detail on what the argument accepts.

  Args:
    name: The name of the argument.
    help_msg: The help message of the argument.
    default: The default value of the message.

  Returns:
    A list of ``arg_utils.Arg`` objects.
  """
  if default is not None:
    default = translation.Translated(default, translate=False)
  return [I18nArg(name, help_msg, optional=True, default=default),
          arg_utils.Arg(
              name + '_en', basestring, help_msg + ' (in English)',
              optional=True,
              default=(default['en-US'] if default else None)),
          arg_utils.Arg(
              name + '_zh', basestring, help_msg + ' (in Chinese)',
              optional=True,
              # default should always have zh-CN when goofy runs. The fallback
              # value is only used when there's no .mo file available (e.g. when
              # in `make doc`.)
              default=(default.get('zh-CN', default['en-US'])
                       if default else None))]


def ParseArg(test, name, backward_compatible=True):
  """Parse arguments for i18n text.

  The argument should either be a string that would be passed to i18n._, or a
  dict looks like:

    {
      'en-US': 'Default English value',
      'zh-CN': 'Chinese Translate'
    }

  The key 'en-US' is mandatory and would be used for locales that don't have
  value specified.

  If backward_compatible is set to True, then the arguments can be specified
  either by ``name``, or by ``name``_en and ``name``_zh. This function
  would parse the arguments into ``name``, and delete the rest.

  Args:
    test: The instance of pytest itself.
    name: The name of the argument, same as argument ``name`` passed to I18nArg
        or BackwardCompatibleI18nArgs.
    backward_compatible: Whether backward compatible mode should be enabled.
  """
  # TODO(pihsun): The argument is always mandatory (or needs a default value)
  #   for now. Add support for optional=True if ever needed.
  # TODO(pihsun): backward_compatible mode should be removed when all tests /
  #   test_lists are migrated to the new format.
  # TODO(pihsun): When merge this back to arg_utils, we can make the call
  #   implicit for I18nArg, so people don't need to call this function manually.
  args = test.args
  arg = getattr(args, name, None)
  name_en = name + '_en'
  name_zh = name + '_zh'

  if backward_compatible and hasattr(args, name_en):
    if arg is not None:
      arg = translation.Translated(arg)

    arg_en = getattr(args, name_en, None)
    arg_zh = getattr(args, name_zh, None) or arg_en
    if arg_en is not None or arg_zh is not None:
      arg_dict = {}
      if arg_en is not None:
        arg_dict['en-US'] = arg_en
      if arg_zh is not None:
        arg_dict['zh-CN'] = arg_zh
    else:
      arg_dict = None

    default = next(a for a in test.ARGS if a.name == name).default

    if (arg_dict != default and arg != default) or (
        default is None and arg is None and arg_dict is None):
      raise ValueError(
          'Please specify exactly one of %s or [%s, %s].' % (
              name, name_en, name_zh))

    if arg_dict != default:
      logging.warn("Use of argument %r: %r and %r: %r is deprecated. "
                   'Please use %r: %r instead.',
                   name_en, arg_en, name_zh, arg_zh, name, arg_dict)
      arg = arg_dict

    delattr(args, name_en)
    delattr(args, name_zh)

  if arg is None:
    raise ValueError('{name} is mandatory.'.format(name=name))

  arg = translation.Translated(arg)
  setattr(args, name, arg)
