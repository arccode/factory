# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Entry point and utilities for Device-Aware API."""

import ast
import inspect
import json
import logging
import os

from cros.factory.utils import config_utils
from cros.factory.device import device_types


DEVICE_MODULE_BASE = 'cros.factory.device'
DEVICE_CONFIG_NAME = 'devices'
# Config types must match the config.json file.
DEVICE_CONFIG_TYPE_DUT = 'dut'
DEVICE_CONFIG_TYPE_STATION = 'station'
DEVICE_CONFIG_TYPE_DEFAULT = DEVICE_CONFIG_TYPE_DUT

# Legacy environment variable name.
ENV_DUT_OPTIONS = 'CROS_FACTORY_DUT_OPTIONS'


class DeviceOptionsError(Exception):
  """Exception for invalid DUT options."""


def _ExtractArgs(func, kargs):
  """Extracts applicable arguments from kargs, according to func's signature.

  This function tries to read argument spec from func, and look up values from
  kargs by the argument names defined for func.

  Arguments
    func: A callable object.
    kargs: A dict object with arguments.

  Returns:
    A dict that can be safely applied to func by func(**kargs)
  """
  spec = inspect.getfullargspec(func)
  if spec.varkw is None:
    # if the function accepts ** arguments, we can just pass everything into it
    # so we only need to filter kargs if spec.keywords is None
    kargs = {k: v for (k, v) in kargs.items() if k in spec.args}
  return kargs


def _GetDeviceClass(module_prefix, class_postfix, class_name):
  """Loads and returns a class object specified from the arguments.

  If the class_name is already a class object, return directly.
  Otherwise, the module and class will be constructed based on the arguments.
  For example, ('links', 'Link', 'ADBLink') would load the class like
    from cros.factory.device.links.adb import ADBLink

  Args:
    module_prefix: The prefix of module path, after DEVICE_MODULE_BASE.
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
  module_path = '.'.join([DEVICE_MODULE_BASE, module_prefix, module_name])
  try:
    class_object = getattr(__import__(module_path, fromlist=[class_name]),
                           class_name)
    return class_object
  except Exception:
    logging.exception('GetDeviceClass')
    raise DeviceOptionsError('Failed to load %s#%s' % (module_path, class_name))


def _ParseOptions(config_type, new_options):
  """Parses Device options and returns the class names and extra args.

  The options usually include:
    - link_class: A string for class name of link or a class object.
    - board_class: A string for class name of board or a class object.
    - And any other options defined by each board and link class.

  When options is empty, find options in following order:

  1. Read options from a "devices.json" using cros.factory.utils.config_utils.
  2. Read from environment variable ENV_DUT_OPTIONS ("CROS_FACTORY_DUT_OPTIONS")
     which may be a python dict or a file path to configuration file.

  Args:
    config_type: The config to read (DEVICE_CONFIG_TYPE_*).
    options: A dictionary of options to create the Device instance.

  Returns:
    A tuple of (link_name, board_name, extra_options)
  """
  options = config_utils.LoadConfig(DEVICE_CONFIG_NAME)

  # Try to load from environment variables (legacy path).
  env_dut_options = os.getenv(ENV_DUT_OPTIONS, '{}').strip()
  if env_dut_options.startswith('{'):
    dut_options = ast.literal_eval(env_dut_options)
  else:
    with open(env_dut_options) as f:
      if env_dut_options.endswith('.json'):
        dut_options = json.load(f)
      else:
        dut_options = ast.literal_eval(f.read())

  # Select target type.
  options = options[config_type]

  # Override configuration.
  if config_type == DEVICE_CONFIG_TYPE_DUT:
    config_utils.OverrideConfig(options, dut_options)
  config_utils.OverrideConfig(options, new_options)

  link_name = options['link_class']
  board_name = options['board_class']
  return (link_name, board_name, options)


def CreateBoardInterface(config_type=DEVICE_CONFIG_TYPE_DEFAULT,
                         **options) -> device_types.DeviceBoard:
  """Returns a board interface for the specified device.

  By default, a :py:class:`cros.factory.device.boards.ChromeOSBoard` object
  is returned, but this may be overridden by setting the options in argument or
  a ``devices.json`` in Device source directory, or
  ``CROS_FACTORY_DUT_OPTIONS`` environment variable in
  ``board_setup_factory.sh``.  See :ref:`board-api-extending`.

  Args:
    config_type: a string to specify the type of Device config to select.
    options: options to setup DUT link and board (see ``_ParseOptions``).

  Returns:
    An instance of the sub-classed DeviceBoard.

  :rtype: cros.factory.device.device_types.DeviceBoard
  """
  link_name, board_name, args = _ParseOptions(config_type, options)
  link_class = _GetDeviceClass('links', 'Link', link_name)
  board_class = _GetDeviceClass('boards', 'Board', board_name)
  link_args = _ExtractArgs(link_class.__init__, args)
  return board_class(link_class(**link_args))


def CreateDUTInterface(**options):
  """Returns a Device board interface from DUT config."""
  return CreateBoardInterface(config_type=DEVICE_CONFIG_TYPE_DUT, **options)


def CreateStationInterface(**options):
  """Returns a Device board interface from Station config."""
  return CreateBoardInterface(config_type=DEVICE_CONFIG_TYPE_STATION, **options)


def CreateDUTLink(**options) -> device_types.DeviceLink:
  """Creates a link object to device under test.

  Args:
    options: Options to setup DUT link (see _ParseOptions).

  Returns:
    An instance of the sub-classede DeviceLink.

  :rtype: cros.factory.device.device_types.DeviceLink
  """
  link_name, unused_name, args = _ParseOptions(DEVICE_CONFIG_TYPE_DUT, options)
  link_class = _GetDeviceClass('links', 'Link', link_name)
  link_args = _ExtractArgs(link_class.__init__, args)
  return link_class(**link_args)


def PrepareDUTLink(**options):
  """Prepares a link connection before that kind of link is ready.

  This provides DUT Link to setup system environment for receiving connections,
  especially when using network-based links.

  Args:
    options: Options to setup DUT link (see _ParseOptions).
  """
  link_name, unused_name, args = _ParseOptions(DEVICE_CONFIG_TYPE_DUT, options)
  link_class = _GetDeviceClass('links', 'Link', link_name)
  prepare_args = _ExtractArgs(link_class.PrepareLink, args)
  return link_class.PrepareLink(**prepare_args)
