# -*- coding: utf-8 -*-
#
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
import re
import socket
import sys
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory import system
from cros.factory.event_log import Log
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test import utils
from cros.factory.test.args import Arg
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager
from cros.factory.test.event import Event
from cros.factory.test.utils import Enum
from cros.factory.utils.process_utils import CheckOutput


_TEST_TITLE = test_ui.MakeLabel('Start Factory Test', u'开始工厂测试')

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
_MSG_INSTALL_INCOMPLETE = test_ui.MakeLabel(
    '<br/>'.join([
        'Factory install process did not complete. Auto-testing stopped.<br/>',
        'Please install the factory test image using the mini-Omaha server',
        'rather than booting from a USB drive.</br>']),
    '<br/>'.join([
        u'安装过程中失败, 停止自動測試。<br/>',
        u'請使用完整的 mini-Omaha 伺服器安裝測試程式，',
        u'不要直接從 USB 碟開機執行。<br/>']),
    'start-font-size test-error')
_MSG_TASK_POWER = test_ui.MakeLabel(
    'Plug in external power to continue.',
    u'请插上外接电源以继续。',
    'start-font-size')
_MSG_TASK_SPACE = test_ui.MakeLabel(
    'Hit SPACE to start testing...',
    u'按 "空白键" 开始测试...',
    'start-font-size')
_MSG_NO_SHOP_FLOOR_SERVER_URL = test_ui.MakeLabel(
    '<br/>'.join([
        'No shop floor server URL. Auto-testing stopped.<br/>',
        'Please install the factory test image using the mini-Omaha server',
        'rather than booting from a USB drive.</br>',
        'For debugging or development, use the listed hot-keys to start',
        'individual tests.']),
    '<br/>'.join([
        u'未指定 shop floor 服务器位址，停止自动测试。<br/>',
        u'请使用完整的 mini-Omaha 服务器安装测试程式，',
        u'不要直接从 USB 碟开机执行。<br/>',
        u'若想除错或执行部份测试，请直接按下对应热键。']),
    'start-font-size test-error')
_MSG_READING_VPD_SERIAL = test_ui.MakeLabel(
    'Reading VPD...', u'讀取 VPD 中...', 'start-font-size')
_MSG_CONTACTING_SERVER = test_ui.MakeLabel(
    'Contacting shop floor server...', u'正在和 shop floor server 联络...',
    r'start-contacting-server')

# Javascripts and HTML for tasks
_JS_SPACE = """
    function enableSpaceKeyPressListener() {
      window.addEventListener(
          "keypress",
          function(event) {
            if (event.keyCode == " ".charCodeAt(0)) {
              window.test.pass();
            }
          });
      window.focus();
    }"""
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
  def __init__(self, test): # pylint: disable=W0231
    self._test = test

  def Run(self):
    self._test.template.SetState(_MSG_TASK_SPACE)
    self._test.ui.RunJS(_JS_SPACE)
    self._test.ui.CallJSFunction('enableSpaceKeyPressListener')


class ExternalPowerTask(FactoryTask):
  """A factory task to wait for external power."""
  AC_CONNECTED = 1
  AC_DISCONNECTED = 2
  AC_CHECK_PERIOD = 0.5

  def __init__(self, test): # pylint: disable=W0231
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
    if system.GetBoard().power.CheckACPresent():
      return self.AC_CONNECTED
    else:
      return self.AC_DISCONNECTED

class FactoryInstallCompleteTask(FactoryTask):
  """A factory task to check if factory install is complete."""
  def __init__(self, test): # pylint: disable=W0231
    self._test = test

  def Run(self):
    if not os.path.exists(_LSB_FACTORY_PATH):
      factory.console.error('%s is missing' % _LSB_FACTORY_PATH)
      self._test.template.SetState(_MSG_INSTALL_INCOMPLETE)
      return

    if self._test.args.has_ectool:
      version_info = utils.CheckOutput(['ectool', 'version'])
      ro_version_output = re.search(r'^RO version:\s*(\S+)$', version_info,
                                    re.MULTILINE)
      rw_version_output = re.search(r'^RW version:\s*(\S+)$', version_info,
                                    re.MULTILINE)
      if (ro_version_output is None or rw_version_output is None
          or ro_version_output.group(1) != rw_version_output.group(1)):
        self._test.template.SetState(_MSG_INSTALL_INCOMPLETE)
        factory.console.info(
            'EC RO and RW version does not match, %s' % version_info)
        return
      Log('factory_installed', ro_version=ro_version_output.group(1),
          rw_version=rw_version_output.group(1))
    else:
      Log('factory_installed')
    self.Pass()


class ShopFloorTask(FactoryTask):
  """A factory task to connect to shopfloor server."""
  def __init__(self, test): # pylint: disable=W0231
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
    prompt_en, prompt_zh = self._test.args.prompt
    prompt_html = test_ui.MakeLabel(prompt_en, prompt_zh, 'start-font-size')
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
    except:
      ShowErrorMsg(sys.exc_info()[1])
    return False


class ReadVPDSerialTask(FactoryTask):
  """If the serial number is already stored in VPD, we can just read it."""
  def __init__(self, test): # pylint: disable=W0231
    self._test = test

  def Run(self):
    serial_number_vpd_keys = self._test.args.serial_number_vpd_keys
    serial_number = None

    def _ReadVPD(key):
      return CheckOutput(['vpd', '-g', key])

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
      else: # If we need multiple VPD entries as the serial number...
        serial_number = dict()
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
    Arg('prompt', tuple,
        'Message to show to the operator when prompting for input.',
        default=('Enter valid serial number:<br/>',
                 u'请输入有效的序号:<br/>'), optional=True),
    Arg('has_ectool', bool, 'Has ectool utility or not.',
        default=True, optional=True)]

  def setUp(self):
    self._task_list = []
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_CSS)
    self.template.SetTitle(_TEST_TITLE)

  def runTest(self):

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
