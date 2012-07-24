# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# DESCRIPTION :
# This factory test runs at the start of a test sequence to verify the DUT has
# been setup correctly.
#
# The start provides several settings (set via darg):
# 'require_external_power': Prompts and waits for external power to be applied.
# 'require_shop_floor': Prompts and waits for serial number as input.  The
#       server is default to the host running mini-omaha, unless you specify an
#       URL by 'shop_floor_server_url' darg.
# 'press_to_continue': Prompts and waits for a key press (SPACE) to continue.

import glob
import os
import socket
import sys
import time
import unittest

from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test import utils
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager
from cros.factory.test.event import Event, EventClient
from cros.factory.event_log import EventLog


_TEST_TITLE = test_ui.MakeLabel('Start Factory Test', u'開始工廠測試')

# Messages for tasks
_MSG_TASK_POWER = test_ui.MakeLabel(
    'Plug in external power to continue.',
    u'請插上外接電源以繼續。',
    'start-font-size')
_MSG_TASK_SERIAL = test_ui.MakeLabel(
    'Enter valid serial number:<br/>',
    u'請輸入有效的序號:<br/>',
    'start-font-size')
_MSG_TASK_SPACE = test_ui.MakeLabel(
    'Hit SPACE to start testing...',
    u'按 "空白鍵" 開始測試...',
    'start-font-size')
_MSG_NO_SHOP_FLOOR_SERVER_URL = test_ui.MakeLabel(
    '<br/>'.join([
        'No shop floor server URL. Auto-testing stopped.<br/>',
        'Please install the factory test image using the mini-Omaha server',
        'rather than booting from a USB drive.</br>',
        'For debugging or development, use the listed hot-keys to start',
        'individual tests.']),
    '<br/>'.join([
        u'未指定 Shop Floor 伺服器位址，停止自動測試。<br/>',
        u'請使用完整的 mini-Omaha 伺服器安裝測試程式，',
        u'不要直接從 USB 碟開機執行。<br/>',
        u'若想除錯或執行部份測試，請直接按下對應熱鍵。']),
    'start-font-size test-error')

# Javascripts and HTML for tasks
_JS_SPACE = '''
    function enableSpaceKeyPressListener() {
      window.addEventListener(
          "keypress",
          function(event) {
            if (event.keyCode == " ".charCodeAt(0)) {
              window.test.pass();
            }
          });
      window.focus();
    }'''
_EVENT_SUBTYPE_SHOP_FLOOR = 'Start-Serial'
_HTML_SHOP_FLOOR = '''
    <input type="text" id="serial" style="height: 2.5em; width: 20em"/>
    <div id="errormsg" class="start-font-size test-error"></div>'''
_JS_SHOP_FLOOR = '''
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
    element.focus();''' % _EVENT_SUBTYPE_SHOP_FLOOR


class PressSpaceTask(FactoryTask):
  def __init__(self, ui, template): # pylint: disable=W0231
    self._ui = ui
    self._template = template

  def Run(self):
    self._template.SetState(_MSG_TASK_SPACE)
    self._ui.RunJS(_JS_SPACE)
    self._ui.CallJSFunction('enableSpaceKeyPressListener')


class ExternalPowerTask(FactoryTask):
  AC_CONNECTED = 1
  AC_DISCONNECTED = 2
  AC_CHECK_PERIOD = 0.5

  def __init__(self, ui, template): # pylint: disable=W0231
    self._ui = ui
    self._template = template

  def Run(self):
    self._template.SetState(_MSG_TASK_POWER)
    while not self.CheckEvent():
      time.sleep(self.AC_CHECK_PERIOD)
    self.Stop()

  def CheckEvent(self):
    state = self.GetExternalPowerState()
    factory.console.info('power state: ', state)
    if state == self.AC_CONNECTED:
      return True
    return False

  def GetExternalPowerState(self):
    for type_file in glob.glob('/sys/class/power_supply/*/type'):
      type_value = utils.ReadOneLine(type_file).strip()
      if type_value == 'Mains':
        status_file = os.path.join(os.path.dirname(type_file), 'online')
        try:
          status = int(utils.ReadOneLine(status_file).strip())
        except ValueError as details:
          raise ValueError('Invalid external power state in %s: %s' %
                           (status_file, details))
        if status == 0:
          return self.AC_DISCONNECTED
        elif status == 1:
          return self.AC_CONNECTED
        else:
          raise ValueError('Invalid external power state "%s" in %s' %
                           (status, status_file))
    raise IOError('Unable to determine external power state.')


class ShopFloorTask(FactoryTask):
  def __init__(self, ui, template, server_url): # pylint: disable=W0231
    self._ui = ui
    self._template = template
    self._server_url = server_url or shopfloor.detect_default_server_url()

  def Run(self):
    # Many developers will try to run factory test image directly without
    # mini-omaha server, so we should either alert and fail, or ask for
    # server address.
    if not self._server_url:
      self._template.SetState(_MSG_NO_SHOP_FLOOR_SERVER_URL)
      return

    shopfloor.set_server_url(self._server_url)
    self._ui.AddEventHandler(_EVENT_SUBTYPE_SHOP_FLOOR,
                             self.ValidateSerialNumber)
    self._template.SetState(_MSG_TASK_SERIAL + _HTML_SHOP_FLOOR)
    self._ui.RunJS(_JS_SHOP_FLOOR)

  def ValidateSerialNumber(self, event):
    # When the input is not valid (or temporary network failure), either
    # return False or raise a ValueError with message to be displayed in
    # bottom status line of input window.
    factory.console.info('Got event: ', event.data)
    serial = event.data

    def ShowErrorMsg(error_msg):
      self._ui.SetHTML(error_msg, id='errormsg')
      self._ui.RunJS(
          'var e = document.getElementById("serial");'
          'e.focus(); e.select();')

    try:
      # All exceptions
      shopfloor.check_serial_number(serial.strip())
      EventLog.ForAutoTest().Log('mlb_serial_number',
                                 serial_number=serial)
      factory.console.info('Serial number: %s' % serial)
      shopfloor.set_serial_number(serial)
      EventClient().post_event(Event(Event.Type.UPDATE_SYSTEM_INFO))
      self.Stop()
      return True
    except shopfloor.ServerFault as e:
      ShowErrorMsg('Server error:<br/>%s' % test_ui.Escape(e.__str__()))
    except ValueError as e:
      ShowErrorMsg(e.message)
    except socket.gaierror as e:
      ShowErrorMsg('Network failure (address error).')
    except socket.error as e:
      ShowErrorMsg('Network failure:<br/>%s' % test_ui.Escape(e[1].__str__()))
    except:
      ShowErrorMsg(sys.exc_info()[1])
    return False


class StartTest(unittest.TestCase):
  def __init__(self, *args, **kwargs):
    super(StartTest, self).__init__(*args, **kwargs)
    self._task_list = []
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._ui.AppendCSS('.start-font-size {font-size: 2em;}')
    self._template.SetTitle(_TEST_TITLE)

    self._press_to_continue = True
    self._require_external_power = False
    self._require_shop_floor = None
    self._shop_floor_server_url = None

  def runTest(self):
    args = self.test_info.args
    self._press_to_continue = args.get('press_to_continue', True)
    self._require_external_power = args.get('require_external_power', False)
    self._require_shop_floor = args.get('require_shop_floor', None)
    self._shop_floor_server_url = args.get('shop_floor_server_url', None)

    # Reset shop floor data only if require_shop_floor is explicitly
    # defined, for test lists using factory_Start multiple times between
    # groups (ex, to prompt for space or check power adapter).
    if self._require_shop_floor is not None:
      shopfloor.reset()
      shopfloor.set_enabled(self._require_shop_floor)

    if self._require_shop_floor:
      self._task_list.append(ShopFloorTask(self._ui,
                                           self._template,
                                           self._shop_floor_server_url))
    if self._require_external_power:
      self._task_list.append(ExternalPowerTask(self._ui, self._template))
    if self._press_to_continue:
      self._task_list.append(PressSpaceTask(self._ui, self._template))

    FactoryTaskManager(self._ui, self._task_list).Run()
