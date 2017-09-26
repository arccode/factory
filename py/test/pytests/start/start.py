# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A test to make sure everything is set for the following test in test list.

Description
-----------
This test checks everything is set for the following tests in the test list,
including make sure an external power supplier is presence, checking factory
software is installed, etc.

Normally, this test should be placed as the first one in a test list, to make
sure everything is set before performing any other tests.

Test Procedure
--------------
It checks several conditions as specified by the options, and ask the operator
to press a key to pass.

Dependency
----------
If argument ``require_external_power`` is set, it reads
``/sys/class/power_supply/`` to determine if an external power supply is
connected.

Examples
--------
To initialize shared data, then ask the operator to press a key to continue::

  OperatorTest(pytest_name='start')

To also ensure if an external power supply is connected, and check factory
toolkit is properly installed::

  OperatorTest(pytest_name='start',
               dargs={'require_external_power': True,
                      'check_factory_install_complete': True})
"""

import logging
import os
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.event_log import Log
from cros.factory.test import factory
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import state
from cros.factory.test.test_task import TestTask
from cros.factory.test.test_task import TestTaskManager
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg


_CSS = """
.start-font-size {
  font-size: 2em;
}
.start-contacting-server {
  background-image: url('/images/active.gif');
  background-repeat: no-repeat;
  padding-left: 18px;
  font-size: 0.75em;
  color: gray;
}
#errormsg {
  margin-top: 12px;
  min-height: 2em;
  font-size: 1.5em;
}
"""

# Messages for tasks
_MSG_INSTALL_INCOMPLETE = i18n_test_ui.MakeI18nLabelWithClass(
    'Factory install process did not complete. Auto-testing stopped.<br><br>'
    'Please install the factory test image using the mini-Omaha server<br>'
    'rather than booting from a USB drive.<br>', 'start-font-size test-error')
_MSG_TASK_POWER = i18n_test_ui.MakeI18nLabelWithClass(
    'Plug in external power to continue.', 'start-font-size')
_MSG_TASK_SPACE = i18n_test_ui.MakeI18nLabelWithClass(
    'Hit SPACE to start testing...', 'start-font-size')
_MSG_INIT_SHARED_DATA = i18n_test_ui.MakeI18nLabelWithClass(
    'Initialize some shared data...', 'start-font-size')

# Javascripts and HTML for tasks
_LSB_FACTORY_PATH = '/usr/local/etc/lsb-factory'


class PressSpaceTask(TestTask):
  """A task to wait for space press event."""

  def __init__(self, test):  # pylint: disable=super-init-not-called
    self._test = test

  def Run(self):
    self._test.template.SetState(_MSG_TASK_SPACE)
    self._test.ui.BindKeyJS(test_ui.SPACE_KEY, 'window.test.pass();')


class ExternalPowerTask(TestTask):
  """A task to wait for external power."""
  AC_CONNECTED = 1
  AC_DISCONNECTED = 2
  AC_CHECK_PERIOD = 0.5

  def __init__(self, test):  # pylint: disable=super-init-not-called
    self._test = test

  def Run(self):
    self._test.template.SetState(_MSG_TASK_POWER)
    while not self.CheckEvent():
      time.sleep(self.AC_CHECK_PERIOD)
    self.Pass()

  def CheckEvent(self):
    power_state = self.GetExternalPowerState()
    logging.info('power state: %s', power_state)
    Log('power_state', state=power_state)
    if power_state == self.AC_CONNECTED:
      return True
    return False

  def GetExternalPowerState(self):
    if self._test.dut.power.CheckACPresent():
      return self.AC_CONNECTED
    else:
      return self.AC_DISCONNECTED


class FactoryInstallCompleteTask(TestTask):
  """A task to check if factory install is complete."""

  def __init__(self, test):  # pylint: disable=super-init-not-called
    self._test = test

  def Run(self):
    if not os.path.exists(_LSB_FACTORY_PATH):
      factory.console.error('%s is missing', _LSB_FACTORY_PATH)
      self._test.template.SetState(_MSG_INSTALL_INCOMPLETE)
      return
    Log('factory_installed')
    self.Pass()


class InitializeSharedData(TestTask):
  """Initialize shared data."""

  def __init__(self, test):  # pylint: disable=super-init-not-called
    self._test = test

  def Run(self):
    self._test.template.SetState(_MSG_INIT_SHARED_DATA)
    for key, value in self._test.args.init_shared_data.iteritems():
      factory.console.debug('set_shared_data[%s] = "%s"', key, value)
      state.set_shared_data(key, value)
    self.Pass()


class StartTest(unittest.TestCase):
  """The factory test to start the whole factory test process."""
  ARGS = [
      Arg('press_to_continue', bool, 'Need to press space to continue',
          default=True, optional=True),
      Arg('require_external_power', bool,
          'Prompts and waits for external power to be applied.',
          default=False, optional=True),
      Arg('check_factory_install_complete', bool,
          'Check factory install process was complete.',
          default=None, optional=True),
      i18n_arg_utils.I18nArg(
          'prompt', 'Message to show to the operator when prompting for input.',
          default=_('Enter valid serial number:<br>')),
      Arg('init_shared_data', dict, 'the shared data to initialize',
          default={}, optional=True)]

  def setUp(self):
    i18n_arg_utils.ParseArg(self, 'prompt')
    self.dut = device_utils.CreateDUTInterface()
    self._task_list = []
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_CSS)

  def runTest(self):

    if self.args.init_shared_data:
      self._task_list.append(InitializeSharedData(self))

    if self.args.check_factory_install_complete:
      self._task_list.append(FactoryInstallCompleteTask(self))

    if self.args.require_external_power:
      self._task_list.append(ExternalPowerTask(self))
    if self.args.press_to_continue:
      self._task_list.append(PressSpaceTask(self))

    TestTaskManager(self.ui, self._task_list).Run()
