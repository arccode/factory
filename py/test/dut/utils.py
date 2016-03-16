#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Utilities for DUT-Aware API."""

import ast
import inspect
import json
import logging
import os

import factory_common  # pylint: disable=W0611
from cros.factory.test.args import Args

ENV_DUT_OPTIONS = 'CROS_FACTORY_DUT_OPTIONS'
LINK_CLASS_LOCAL = 'LocalLink'
DEFAULT_DUT_OPTIONS = '{}'
DEFAULT_LINK_CLASS = LINK_CLASS_LOCAL
DEFAULT_BOARD_CLASS = 'ChromeOSBoard'
DUT_MODULE_BASE = 'cros.factory.test.dut'


class DUTOptionsError(Exception):
  """Exception for invalid DUT options."""
  pass


def _ExtractArgs(func, kargs):
  spec = inspect.getargspec(func)
  if spec.keywords is None:
    # if the function accepts ** arguments, we can just pass everything into it
    # so we only need to filter kargs if spec.keywords is None
    kargs = {k: v for (k, v) in kargs.iteritems() if k in spec.args}
  return kargs


def _GetDUTClass(module_prefix, class_postfix, class_name):
  """Loads and returns a class object specified from the arguments.

  If the class_name is already a class object, return directly.
  Otherwise, the module and class will be constructed based on the arguments.
  For example, ('links', 'Link', 'ADBLink') would load the class like
    from cros.factory.test.dut.links.adb import ADBLink

  Args:
    module_prefix: The prefix of module path, after DUT_MODULE_BASE.
    class_postfix: The postfix of class to be removed for module name.
    class_name: A string for name of the class to load, or a class object.

  Returns:
    A class constructor from the arguments.
  """
  if callable(class_name):
    return class_name
  assert class_name.endswith(class_postfix), ('Unknown class name: %s' %
                                              class_name)
  module_name = class_name[:-len(class_postfix)].lower()
  module_path = '.'.join([DUT_MODULE_BASE, module_prefix, module_name])
  try:
    class_object = getattr(__import__(module_path, fromlist=[class_name]),
                           class_name)
    return class_object
  except:
    logging.exception('GetDUTClass')
    raise DUTOptionsError('Failed to load %s#%s' % (module_path, class_name))


def _ParseOptions(options):
  """Parses DUT options and returns the class names and extra args.

  The options usually include:
    - link_class: A string for class name of link or a class object.
    - board_class: A string for class name of board or a class object.
    - And any other options defined by each board and link class.

  When options is empty, read from environment variable ENV_DUT_OPTIONS
  ("CROS_FACTORY_DUT_OPTIONS"). The environment variable can be a python dict,
  or a file path of configuration file.

  Both JSON and Python AST dict are supported.

  Args:
    options: A dictionary of options to create the DUT.

  Returns:
    A tuple of (link_name, board_name, extra_options)
  """
  if not options:
    # Try to load from environment.
    option_string = os.getenv(ENV_DUT_OPTIONS, DEFAULT_DUT_OPTIONS).strip()
    if option_string.startswith('{'):
      options = ast.literal_eval(option_string)
    else:
      with open(option_string) as f:
        if option_string.endswith('.json'):
          options = json.load(f)
        else:
          options = ast.literal_eval(f.read())

  link_name = options.pop('link_class', DEFAULT_LINK_CLASS)
  board_name = options.pop('board_class', DEFAULT_BOARD_CLASS)
  return (link_name, board_name, options)


def CreateBoard(**options):
  """Returns a board instance for the device under test.

  By default, a :py:class:`cros.factory.test.dut.boards.ChromeOSBoard` object
  is returned, but this may be overridden by setting the options in argument or
  ``CROS_FACTORY_DUT_OPTIONS`` environment variable in
  ``board_setup_factory.sh``.  See :ref:`board-api-extending`.

  Args:
    options: options to setup DUT link and board (see ``_ParseOptions``).

  Returns:
    An instance of the sub-classed DUTBoard.

  :rtype: cros.factory.test.dut.board.DUTBoard
  """
  link_name, board_name, args = _ParseOptions(options)
  link_class = _GetDUTClass('links', 'Link', link_name)
  board_class = _GetDUTClass('boards', 'Board', board_name)
  link_args = _ExtractArgs(link_class.__init__, args)
  return board_class(link_class(**link_args))


def CreateLocalBoard(**options):
  """Returns a board instance for the local host.

  Defaults to create the board using DEFAULT_BOARD_CLASS.

  Args:
    options: options to setup DUT board (see ``_ParseOptions``).

  Returns:
    An instance of the sub-classed DUTBoard.

  :rtype: cros.factory.test.dut.board.DUTBoard
  """
  options.update('link_class', LOCAL_LINK_CLASS)
  return CreateBoard(options)


def CreateLink(**options):
  """Creates a link object.

  Args:
    options: Options to setup DUT link (see _ParseOptions).

  Returns:
    An instance of the sub-classede DUTLink.

  :rtype: cros.factory.test.dut.link.DUTLink
  """
  link_name, board_name, args = _ParseOptions(options)
  link_class = _GetDUTClass('links', 'Link', link_name)
  link_args = _ExtractArgs(link_class.__init__, args)
  return link_class(**link_args)


def PrepareLink(**options):
  """Prepares a link connection before that kind of link is ready.

  This provides DUT Link to setup system environment for receiving connections,
  especially when using network-based links.

  Args:
    options: Options to setup DUT link (see _ParseOptions).
  """
  link_name, board_name, args = _ParseOptions(options)
  link_class = _GetDUTClass('links', 'Link', link_name)
  prepare_args = _ExtractArgs(link_class.PrepareLink, args)
  return link_class.PrepareLink(**prepare_args)
