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
To initialize shared data, then ask the operator to press a key to continue,
add this in test list::

  {
    "pytest_name": "start"
  }

To also ensure if an external power supply is connected, and check factory
toolkit is properly installed::

  {
    "pytest_name": "start",
    "args": {
      "check_factory_install_complete": true,
      "require_external_power": true
    }
  }
"""

import logging
import os

from six import iteritems

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.event_log import Log
from cros.factory.test import session
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import log_utils


_LSB_FACTORY_PATH = '/usr/local/etc/lsb-factory'
_AC_CHECK_PERIOD = 0.5


class StartTest(test_case.TestCase):
  """The factory test to start the whole factory test process."""
  ARGS = [
      Arg('press_to_continue', bool, 'Need to press space to continue',
          default=True),
      Arg('require_external_power', bool,
          'Prompts and waits for external power to be applied.',
          default=False),
      Arg('check_factory_install_complete', bool,
          'Check factory install process was complete.',
          default=None),
      i18n_arg_utils.I18nArg(
          'prompt', 'Message to show to the operator when prompting for input.',
          default=_('Enter valid serial number:<br>')),
      Arg('init_shared_data', dict, 'the shared data to initialize',
          default={})]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.ui.ToggleTemplateClass('font-large', True)

  def runTest(self):
    if self.args.init_shared_data:
      self.InitializeSharedData()

    if self.args.check_factory_install_complete:
      self.CheckFactoryInstallComplete()

    if self.args.require_external_power:
      self.CheckExternalPower()

    if self.args.press_to_continue:
      self.ui.SetState(_('Hit SPACE to start testing...'))
      self.ui.WaitKeysOnce(test_ui.SPACE_KEY)

  def CheckExternalPower(self):
    logger = log_utils.NoisyLogger(logging.info)
    self.ui.SetState(_('Plug in external power to continue.'))

    while True:
      ac_present = self.dut.power.CheckACPresent()
      logger.Log('power state: %s', ac_present)
      Log('ac_present', state=ac_present)
      if ac_present:
        break
      self.Sleep(_AC_CHECK_PERIOD)

  def CheckFactoryInstallComplete(self):
    if not os.path.exists(_LSB_FACTORY_PATH):
      session.console.error('%s is missing', _LSB_FACTORY_PATH)
      self.ui.SetState([
          '<span class="test-error">',
          _('Factory install process did not complete. '
            'Auto-testing stopped.<br><br>'
            'Please install the factory test image using factory server<br>'
            'rather than booting from a USB drive.<br>'), '</span>'
      ])
      # hangs forever.
      self.WaitTaskEnd()
    Log('factory_installed')

  def InitializeSharedData(self):
    self.ui.SetState(_('Initialize some shared data...'))
    for key, value in iteritems(self.args.init_shared_data):
      session.console.debug('DataShelfSetValue[%s] = "%s"', key, value)
      state.DataShelfSetValue(key, value)
