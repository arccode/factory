# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory test automation module."""

import logging
import os
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.common import MakeList
from cros.factory.hwid import common
from cros.factory.test import factory
from cros.factory.test import utils
from cros.factory.test.e2e_test import e2e_test
from cros.factory.test.e2e_test.common import AutomationMode, DEFAULT, CHROOT


AUTOMATION_FUNCTION_KWARGS_FILE = os.path.join(
    factory.get_state_root(), 'automation_function_kwargs.yaml')


class AutomationError(Exception):
  """Automation error."""
  pass


class AutomatorMetaclass(e2e_test.E2ETestMetaclass):
  """Metaclass for Automator class.

  This metaclass is used to hold the cache for board automation function map.
  The cache is copied to the created Automator subclass after the subclass
  object is created, and is reset to empty after copy.
  """
  automator_registry = {}

  def __init__(mcs, name, bases, attrs):
    # Copy the constructed board automation function map cache to the automator
    # subclass and reset the cache.
    mcs.automator_for_board = AutomatorMetaclass.automator_registry
    AutomatorMetaclass.automator_registry = {}
    super(AutomatorMetaclass, mcs).__init__(name, bases, attrs)


class AutomatorSetting(object):
  """A class to hold the settings for a board automation function."""
  def __init__(self, function, override_dargs=None,
               automation_mode=AutomationMode.PARTIAL,
               wait_for_factory_test=True):
    self.function = function
    self.override_dargs = override_dargs or {}
    if not automation_mode in AutomationMode:
      raise AutomationError('Invalid automation mode %r' % automation_mode)
    self.automation_mode = automation_mode
    self.wait_for_factory_test = wait_for_factory_test


class Automator(e2e_test.E2ETest):
  """The base automator class."""
  __metaclass__ = AutomatorMetaclass

  automator_for_board = None

  def runTest(self):
    """The main automator method.

    This method tries to locate and start the automation function with the
    following logic:

        1) Look for an automation function with current enabled automation mode
           of the current board.
        2) If not automation function is found in 1), look for an automation
           function with current enabled automation mode in DEFAULT board.
        3) If an automation function is found, start it.
        4) If no automation function was found, start the factory test and wait
           for it to pass.
    """
    if utils.in_chroot():
      board = CHROOT
    else:
      board = common.ProbeBoard()

    automator_setting = None
    path = self.test_info.path
    mode = self.test_info.automation_mode

    for b in (board, DEFAULT):
      if b in self.automator_for_board:
        setting = self.automator_for_board[b].get(mode)
        if setting:
          automator_setting = setting
          break

    # Start factory test.
    dargs = automator_setting.override_dargs if automator_setting else {}
    self._InitFactoryTest(dargs=dargs)
    self.StartFactoryTest()

    if automator_setting:
      logging.info('Start %s automation function for factory test %r.',
                   mode, self.test_info.pytest_name)
      # If AUTOMATION_FUNCTION_KWARGS_FILE exists, try to load kwargs for the
      # automation function.
      kwargs = {}
      if os.path.exists(AUTOMATION_FUNCTION_KWARGS_FILE):
        with open(AUTOMATION_FUNCTION_KWARGS_FILE) as f:
          automation_function_kwargs = yaml.safe_load(f.read())
          kwargs.update(automation_function_kwargs.get(path, {}))

      automator_setting.function(self, **kwargs)
      if automator_setting.wait_for_factory_test:
        self.pytest_thread.join()
        self.WaitForPass()
    else:
      logging.warn('Factory test %r does not have %s automation function. '
                   'Simply wait for the factory test to end.',
                   self.test_info.pytest_name, mode)
      self.pytest_thread.join()
      self.WaitForPass()


def AutomationFunction(boards=(DEFAULT,), override_dargs=None,
                       automation_mode=AutomationMode.PARTIAL,
                       wait_for_factory_test=True):
  """A decorator to create a test automation function.

  Args:
    boards: The list of boards this automation function is for.
    override_dargs: A dict of dargs to override.
    automation_mode: The list of automation mode under which this automation
      function is enabled
    wait_for_factory_test: Whether to wait for the factory test to finish.

  Returns:
    A decorator for automation function.
  """
  def Decorator(automation_function):
    if not automation_function.__name__.startswith('automate'):
      raise AutomationError(
          ('Invalid automation function: %r: automation function\'s name '
           'must start with "automate"') % automation_function.__name__)

    modes = MakeList(automation_mode)

    for board in boards:
      registry = AutomatorMetaclass.automator_registry
      if board in registry:
        for mode in modes:
          if mode in registry[board]:
            existing_function = registry[board][mode].function
            raise AutomationError(
                ('More than one automation function (%r and %r) registered '
                 'for board %r of mode %r') % (
                     existing_function.function.__name__,
                     automation_function.__name__, board, mode))
      else:
        registry[board] = {}

      for mode in modes:
        AutomatorMetaclass.automator_registry[board][mode] = (
            AutomatorSetting(automation_function,
                             override_dargs=override_dargs,
                             automation_mode=mode,
                             wait_for_factory_test=wait_for_factory_test))
    return automation_function

  return Decorator
