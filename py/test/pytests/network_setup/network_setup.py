#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A pytest to wait operators setup network connection.

The interface settings are saved in a JSON config file, the JSON schema for this
config file is `py/test/pytests/network_setup/network_config.schema.json`.
Usage::

    --- py/test/pytests/network_setup/fft_network_config.json ---
    {
      "eth1": {
        "address": "10.0.1.3",
        "prefixlen": 24
      },
      "/sys/devices/pci0000:00/0000:00:14.0/usb1/1-1/1-1:1.0/net": {
        "address": "10.0.2.1",
        "prefixlen": 24,
        "gateway": "10.0.2.254"
      }
    }
    --- in test list ---
    OperatorTest(
      id='NetworkSetup',
      pytest_name='network_setup.network_setup',
      dargs={
        'config_name': 'fft_network_config'
      })
"""

import logging
import threading
import traceback
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import connection_manager
from cros.factory.utils import arg_utils
from cros.factory.utils import config_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils


_TITLE = test_ui.MakeLabel('Setup network connection', u'设定网络连线')

_ID_SUBTITLE_DIV = 'subtitle'
_ID_MESSAGE_DIV = 'message'
_ID_INSTRUCTION_DIV = 'instruction'

_STATE_HTML = """
<div id='%s'></div>
<div id='%s'></div>
<div id='%s'></div>
""" % (_ID_SUBTITLE_DIV, _ID_MESSAGE_DIV, _ID_INSTRUCTION_DIV)

def _GetSubtitleForInterface(interface):
  interface = '<b>%s</b>' % interface
  return test_ui.MakeLabel(
      'Setting up interface %s' % interface,
      u'正在设定网络介面 %s' % interface)

_PRESS_SPACE = test_ui.MakeLabel(
    'Press space to continue', u'请按空白键继续')


ErrorCode = connection_manager.ConnectionManagerException.ErrorCode

def _ErrorCodeToMessage(error_code, interface):
  interface = '<b>%s</b>' % interface
  if error_code == ErrorCode.NO_PHYSICAL_LINK:
    return test_ui.MakeLabel(
        'No physical link on %s' % interface,
        u'%s 没有连接网络线' % interface),
  if error_code == ErrorCode.INTERFACE_NOT_FOUND:
    return test_ui.MakeLabel(
        'Interface %s not found' % interface,
        u'找不到网络介面 %s' % interface),
  if error_code == ErrorCode.NO_SELECTED_SERVICE:
    return test_ui.MakeLabel(
        'Interface %s not initialized' % interface,
        u'网络介面 %s 未成功初始化' % interface),


class NetworkConnectionSetup(unittest.TestCase):
  ARGS = [
      arg_utils.Arg('config_name', str, 'path to the config file'),
      arg_utils.Arg('timeout_secs', float,
                    'timeout seconds for each interface, default is no timeout',
                    default=None),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.ui_template = ui_templates.OneSection(self.ui)
    self.space_pressed = threading.Event()

  def runTest(self):
    self.ui_template.SetTitle(_TITLE)
    self.ui_template.SetState(_STATE_HTML)
    self.ui.BindKey(test_ui.SPACE_KEY, lambda _: self.space_pressed.set())
    process_utils.StartDaemonThread(target=self.SetInterfaces)
    self.ui.Run()

  def SetInterfaces(self):
    try:
      settings = config_utils.LoadConfig(config_name=self.args.config_name,
                                         schema_name='network_config')

      proxy = state.get_instance()
      if not proxy.IsPluginRunning('connection_manager'):
        logging.info('Goofy plugin %r is not running, create our own instance')
        proxy = connection_manager.ConnectionManager()

      for interface in settings:
        interface_name = settings[interface].pop('interface_name', interface)
        self.ui.SetHTML(_GetSubtitleForInterface(interface),
                        id=_ID_SUBTITLE_DIV)

        def _TryOnce(interface=interface, interface_name=interface_name):
          error_code = proxy.SetStaticIP(interface_or_path=interface,
                                         **settings[interface])
          if error_code is None:
            return True
          # Hint operators what might go wrong.
          self.ui.SetHTML(_ErrorCodeToMessage(error_code, interface_name),
                          id=_ID_MESSAGE_DIV)

        # Try once first, if we success, we don't need to ask operators to do
        # anything.
        try:
          success = _TryOnce()
        except Exception:
          success = False

        if not success:
          # Failed, wait operators to press space when they think cables are
          # connected correctly.
          self.ui.SetHTML(_PRESS_SPACE, id=_ID_INSTRUCTION_DIV)
          self.space_pressed.clear()
          self.space_pressed.wait()

          # Polling until success or timeout (operators don't need to press
          # space anymore).
          sync_utils.PollForCondition(_TryOnce,
                                      timeout_secs=self.args.timeout_secs)
      self.ui.Pass()
    except:  # pylint: disable=bare-except
      self.ui.Fail(traceback.format_exc())
