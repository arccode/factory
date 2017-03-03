# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The 'start' factory test.

This factory test runs at the start of a test sequence to verify the DUT has
been setup correctly.

The start provides several settings (set via darg):
  'require_external_power': Prompts and waits for external power to be applied.
  'require_shop_floor': Prompts and waits for serial number as input.
  'check_factory_install_complete': Check factory install process was complete.
  'press_to_continue': Prompts and waits for a key press (SPACE) to continue.
"""

import logging
import os
import socket
import sys
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.event import Event
from cros.factory.test.event_log import Log
from cros.factory.test import factory
from cros.factory.test.factory_task import FactoryTask
from cros.factory.test.factory_task import FactoryTaskManager
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils.type_utils import Enum


_TEST_TITLE = i18n_test_ui.MakeI18nLabel('Start Factory Test')

_CSS = """
.start-font-size {
  font-size: 2em;
}
.start-contacting-server {
  background-image: url('/images/active.gif');
  background-repeat: no-repeat;
  padding-left: 18px;
  font-size: 12px;
  color: gray;
}
#errormsg {
  margin-top: 12px;
  min-height: 2em;
  font-size: 150%;
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
_MSG_NO_SHOP_FLOOR_SERVER_URL = i18n_test_ui.MakeI18nLabelWithClass(
    'No shop floor server URL. Auto-testing stopped.<br><br>'
    'Please install the factory test image using the mini-Omaha server<br>'
    'rather than booting from a USB drive.<br><br>'
    'For debugging or development, use the listed hot-keys to start<br>'
    'individual tests.', 'start-font-size test-error')
_MSG_READING_VPD_SERIAL = i18n_test_ui.MakeI18nLabelWithClass('Reading VPD...',
                                                              'start-font-size')
_MSG_CONTACTING_SERVER = i18n_test_ui.MakeI18nLabelWithClass(
    'Contacting shop floor server...', r'start-contacting-server')
_MSG_INIT_SHARED_DATA = i18n_test_ui.MakeI18nLabelWithClass(
    'Initialize some shared data...', 'start-font-size')

# Javascripts and HTML for tasks
_EVENT_SUBTYPE_SHOP_FLOOR = 'Start-Serial'
_HTML_SHOP_FLOOR = """
    <input type="text" id="serial" style="height: 2.5em; width: 20em"/>
    <div id="errormsg" class="test-error"></div>"""
_JS_SHOP_FLOOR = """
    function submit() {
      var text = document.getElementById("serial");
      window.test.sendTestEvent("%s", text.value);
    }
    function shopfloorError(msg) {
      var element = document.getElementById("errormsg");
      element.innerHTML = msg;
    }
    var element = document.getElementById("serial");
    element.addEventListener("keypress", function(event) {
      if (event.keyCode == 13) {
        submit();
      }
    })
    element.focus();""" % _EVENT_SUBTYPE_SHOP_FLOOR
_LSB_FACTORY_PATH = '/usr/local/etc/lsb-factory'


class PressSpaceTask(FactoryTask):
  """A factory task to wait for space press event."""

  def __init__(self, test):  # pylint: disable=super-init-not-called
    self._test = test

  def Run(self):
    self._test.template.SetState(_MSG_TASK_SPACE)
    self._test.ui.BindKeyJS(test_ui.SPACE_KEY, 'window.test.pass();')


class ExternalPowerTask(FactoryTask):
  """A factory task to wait for external power."""
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
    state = self.GetExternalPowerState()
    logging.info('power state: %s', state)
    Log('power_state', state=state)
    if state == self.AC_CONNECTED:
      return True
    return False

  def GetExternalPowerState(self):
    if self._test.dut.power.CheckACPresent():
      return self.AC_CONNECTED
    else:
      return self.AC_DISCONNECTED


class FactoryInstallCompleteTask(FactoryTask):
  """A factory task to check if factory install is complete."""

  def __init__(self, test):  # pylint: disable=super-init-not-called
    self._test = test

  def Run(self):
    if not os.path.exists(_LSB_FACTORY_PATH):
      factory.console.error('%s is missing', _LSB_FACTORY_PATH)
      self._test.template.SetState(_MSG_INSTALL_INCOMPLETE)
      return
    Log('factory_installed')
    self.Pass()


class ShopFloorTask(FactoryTask):
  """A factory task to connect to shopfloor server."""

  def __init__(self, test):  # pylint: disable=super-init-not-called
    self._test = test

  def Run(self):
    # Many developers will try to run factory test image directly without
    # mini-omaha server, so we should either alert and fail, or ask for
    # server address.
    if not shopfloor.get_server_url():
      self._test.template.SetState(_MSG_NO_SHOP_FLOOR_SERVER_URL)
      return

    self._test.ui.AddEventHandler(_EVENT_SUBTYPE_SHOP_FLOOR,
                                  self.ValidateSerialNumber)
    prompt = self._test.args.prompt
    prompt_html = i18n_test_ui.MakeI18nLabel(
        prompt, _css_class='start-font-size')
    self._test.template.SetState(prompt_html + _HTML_SHOP_FLOOR)
    self._test.ui.RunJS(_JS_SHOP_FLOOR)

  def ValidateSerialNumber(self, event):
    # When the input is not valid (or temporary network failure), either
    # return False or raise a ValueError with message to be displayed in
    # bottom status line of input window.
    serial = event.data

    self._test.ui.SetHTML(_MSG_CONTACTING_SERVER, id='errormsg')
    self._test.ui.RunJS('$("serial").disabled = true')

    def ShowErrorMsg(error_msg):
      self._test.ui.SetHTML(error_msg, id='errormsg')
      self._test.ui.RunJS(
          'var e = document.getElementById("serial");'
          'e.focus(); e.select(); e.disabled = false')

    try:
      # All exceptions
      shopfloor.check_serial_number(serial.strip())
      Log('mlb_serial_number', serial_number=serial)
      logging.info('Serial number: %s', serial)
      shopfloor.set_serial_number(serial)
      self._test.ui.event_client.post_event(
          Event(Event.Type.UPDATE_SYSTEM_INFO))
      self.Pass()
      return True
    except shopfloor.ServerFault as e:
      ShowErrorMsg('Server error: %s' % test_ui.Escape(e.__str__()))
    except ValueError as e:
      ShowErrorMsg(e.message)
    except socket.gaierror as e:
      ShowErrorMsg('Network failure (address error).')
    except socket.error as e:
      ShowErrorMsg('Network failure: %s' % test_ui.Escape(e[1].__str__()))
    except Exception:
      ShowErrorMsg(sys.exc_info()[1])
    return False


class ReadVPDSerialTask(FactoryTask):
  """If the serial number is already stored in VPD, we can just read it."""

  def __init__(self, test):  # pylint: disable=super-init-not-called
    self._test = test

  def Run(self):
    serial_number_vpd_keys = self._test.args.serial_number_vpd_keys
    serial_number = None

    def _ReadVPD(key):
      return process_utils.CheckOutput(['vpd', '-g', key])

    if serial_number_vpd_keys:
      self._test.template.SetState(_MSG_READING_VPD_SERIAL)
      if (type(serial_number_vpd_keys) == str or
          type(serial_number_vpd_keys) == unicode):
        vpd_value = _ReadVPD(serial_number_vpd_keys)
        if not vpd_value:
          self.Fail('VPD value of %s is empty.' % serial_number_vpd_keys)
          return
        else:
          serial_number = vpd_value
      else:  # If we need multiple VPD entries as the serial number...
        serial_number = {}
        for v in serial_number_vpd_keys:
          vpd_value = _ReadVPD(v)
          if not vpd_value:
            self.Fail('VPD value of %s is empty.' % v)
            return
          else:
            serial_number[v] = vpd_value

    Log('mlb_serial_number', serial_number=serial_number)
    shopfloor.set_serial_number(serial_number)
    self._test.ui.event_client.post_event(Event(Event.Type.UPDATE_SYSTEM_INFO))
    self.Pass()


class InitializeSharedData(FactoryTask):
  """Initialize shared data."""

  def __init__(self, test):  # pylint: disable=super-init-not-called
    self._test = test

  def Run(self):
    self._test.template.SetState(_MSG_INIT_SHARED_DATA)
    for key, value in self._test.args.init_shared_data.iteritems():
      factory.console.debug('set_shared_data[%s] = "%s"', key, value)
      factory.set_shared_data(key, value)
    self.Pass()


class StartTest(unittest.TestCase):
  """The factory test to start the whole factory test process."""
  ARGS = [
      Arg('press_to_continue', bool, 'Need to press space to continue',
          default=True, optional=True),
      Arg('require_external_power', bool,
          'Prompts and waits for external power to be applied.',
          default=False, optional=True),
      Arg('require_shop_floor', Enum([True, False, 'defer']),
          'Prompts and waits for serial number as input if no VPD keys are '
          'provided as serial numbers, or reads serial numbers from VPD. '
          'This may be set to True, or "defer" to enable shopfloor but skip '
          'reading the serial number.',
          default=None, optional=True),
      Arg('check_factory_install_complete', bool,
          'Check factory install process was complete.',
          default=None, optional=True),
      Arg('serial_number_vpd_keys', (str, unicode, list),
          'A string or list of strings indicating a set of VPDs that are used '
          'as the key to fetch data from shop floor proxy.',
          default=None, optional=True),
      i18n_arg_utils.I18nArg(
          'prompt', 'Message to show to the operator when prompting for input.',
          default=_('Enter valid serial number:<br>'),
          accept_tuple=True),
      Arg('init_shared_data', dict, 'the shared data to initialize',
          default={}, optional=True)]

  def setUp(self):
    i18n_arg_utils.ParseArg(self, 'prompt')
    self.dut = device_utils.CreateDUTInterface()
    self._task_list = []
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_CSS)
    self.template.SetTitle(_TEST_TITLE)

  def runTest(self):

    if self.args.init_shared_data:
      self._task_list.append(InitializeSharedData(self))

    # Reset shop floor data only if require_shop_floor is explicitly
    # defined, for test lists using factory_Start multiple times between
    # groups (ex, to prompt for space or check power adapter).
    if self.args.require_shop_floor is not None:
      shopfloor.set_enabled(self.args.require_shop_floor)

    if (self.args.require_shop_floor and
        self.args.require_shop_floor != 'defer'):
      if self.args.serial_number_vpd_keys:
        self._task_list.append(ReadVPDSerialTask(self))
      else:
        self._task_list.append(ShopFloorTask(self))

    if self.args.check_factory_install_complete:
      self._task_list.append(FactoryInstallCompleteTask(self))

    if self.args.require_external_power:
      self._task_list.append(ExternalPowerTask(self))
    if self.args.press_to_continue:
      self._task_list.append(PressSpaceTask(self))

    FactoryTaskManager(self.ui, self._task_list).Run()
