# -*- coding: utf-8 -*-
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Raiden CC line polarity check and operation flip test.

Firstly checks Raiden cable connected direction is right by CC polarity, and
also be able to show operation instruction for cable flipping to test another
CC line.

For double CC cable, this test can flip CC automatically or you can set Arg
double_cc_flip_target as 'CC1' or 'CC2' to indicate the final CC position.
Moreover, if test scheme can guarantee double CC cable connection is not
twisted, that is, Plankton CC1 is connected to DUT CC1, then it can set Arg
double_cc_quick_check as True to accelerate the test.
"""

import logging
import time
import unittest

import factory_common  # pylint: disable=W0611

from cros.factory.test import countdown_timer
from cros.factory.test import dut
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.fixture import bft_fixture
from cros.factory.utils import process_utils

_TEST_TITLE = test_ui.MakeLabel('Raiden CC Detect', u'Raiden CC 检查')
_OPERATION = test_ui.MakeLabel('Flip Raiden cable and plug in again...',
                               u'将 Raiden port 头反转后再次插入机器...')
_NO_TIMER = test_ui.MakeLabel('And press Enter key to continue...',
                              u'并按 Enter 键继续...')
_CSS = 'body { font-size: 2em; }'

_ID_OPERATION_DIV = 'operation_div'
_ID_COUNTDOWN_DIV = 'countdown_div'
_STATE_HTML = '<div id="%s"></div><div id="%s"></div>' % (
    _ID_OPERATION_DIV, _ID_COUNTDOWN_DIV)


class RaidenCCFlipCheck(unittest.TestCase):
  """Raiden CC line polarity check and operation flip test."""
  ARGS = [
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP),
      Arg('adb_remote_test', bool, 'Run test against remote ADB target.',
          default=False),
      Arg('raiden_index', int, 'Index of DUT raiden port'),
      Arg('original_enabled_cc', str, 'Original enabled CC line.',
          default='CC1'),
      Arg('ask_flip_operation', bool,
          'Determine whether to ask operator to flip cable.',
          default=False),
      Arg('double_cc_flip_target', str,
          'If using double CC cable, set either "CC1" or "CC2" for the target '
          'to flip. Flip anyway if this is not set.',
          optional=True),
      Arg('double_cc_quick_check', bool,
          'If using double CC cable, set True if you guarantee CC pair is not '
          'reversed. CC polarity in Plankton side implies DUT side.',
          default=False),
      Arg('timeout_secs', int,
          'Timeout seconds for operation, set 0 for operator pressing enter '
          'key to finish operation.',
          default=0),
      Arg('state_src_ready', int, 'State number of pd state SRC_READY.',
          default=22)
  ]

  def setUp(self):
    self._dut = dut.Create()
    self._ui = test_ui.UI(css=_CSS)
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    if self.args.ask_flip_operation and self.args.timeout_secs == 0:
      self._ui.BindKey(test_ui.ENTER_KEY, lambda _: self.OnEnterPressed())
    self._bft_fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)
    self._adb_remote_test = self.args.adb_remote_test
    self._double_cc_quick_check = (
        self._bft_fixture.IsDoubleCCCable() and self.args.double_cc_quick_check)
    if (not self._bft_fixture.IsParallelTest() and
        not self._double_cc_quick_check):
      # No preparation is required for parallel test.
      if self._adb_remote_test:
        # For remote test, keep adb connection enabled.
        self._bft_fixture.SetDeviceEngaged('ADB_HOST', engage=True)
      else:
        self._bft_fixture.SetDeviceEngaged('USB3', engage=True)
      time.sleep(1)  # Wait for PD negotiate and settle down
    self._polarity = self.GetCCPolarity()
    logging.info('Initial polarity: %s', self._polarity)

  def GetCCPolarity(self):
    """Gets enabled CC line for raiden port arg.raiden_index.

    Returns:
      'CC1' or 'CC2', or 'UNCONNECTED' if it doesn't detect SRC_READY.
    """
    # For double CC cable, if we guarantee CC pair is not reversed, polarity in
    # Plankton side implies DUT side.
    if self._double_cc_quick_check:
      return self._bft_fixture.GetPDState()['polarity']

    port_status = self._dut.usb_c.GetPDStatus(self.args.raiden_index)
    # For newer version EC, port_status[state] will return string instead of
    # state number.
    if self._adb_remote_test or self._bft_fixture.IsParallelTest():
      # For remote or parallel test, just feedback polarity.
      return port_status['polarity']
    if (port_status['state'] == self.args.state_src_ready or
        port_status['state'] == 'SRC_READY'):
      return port_status['polarity']
    logging.info('Detected port state is not state_src_ready (expect: %d, '
                 'got: %d).',
                 self.args.state_src_ready, port_status['state'])
    return 'UNCONNECTED'

  def tearDown(self):
    self._bft_fixture.Disconnect()

  def _PollCheckCCPolarity(self):
    while True:
      time.sleep(0.5)
      polarity = self.GetCCPolarity()
      if polarity != self._polarity and polarity != 'UNCONNECTED':
        self._polarity = polarity
        self._ui.Pass()

  def OnEnterPressed(self):
    polarity = self.GetCCPolarity()
    if polarity != self._polarity and polarity != 'UNCONNECTED':
      self._polarity = polarity
      self._ui.Pass()
    else:
      self._ui.Fail('DUT does not detect cable flipped. Was it really flipped?')

  def runTest(self):
    if (self._polarity != self.args.original_enabled_cc and
        not self._bft_fixture.IsDoubleCCCable()):
      self.fail('Original polarity is wrong (expect: %s, got: %s). '
                'Does Raiden cable connect in correct direction?' %
                (self.args.original_enabled_cc, self._polarity))

    if self.args.ask_flip_operation:
      self._template.SetState(_STATE_HTML)
      self._ui.SetHTML(_OPERATION, id=_ID_OPERATION_DIV)
      if self.args.timeout_secs == 0:
        self._ui.SetHTML(_NO_TIMER, id=_ID_COUNTDOWN_DIV)
      else:
        # Start countdown timer.
        countdown_timer.StartCountdownTimer(
            self.args.timeout_secs,
            lambda: self._ui.Fail('Timeout waiting for test to complete'),
            self._ui,
            _ID_COUNTDOWN_DIV)
        # Start polling thread
        process_utils.StartDaemonThread(target=self._PollCheckCCPolarity)
      self._ui.Run()
    elif (self._bft_fixture.IsDoubleCCCable() and
          (not self.args.double_cc_flip_target or
           self._polarity != self.args.double_cc_flip_target)):
      factory.console.info('Double CC test, doing CC flip...')
      self._bft_fixture.SetMuxFlip(0)
      time.sleep(1)
      if self._adb_remote_test and not self._double_cc_quick_check:
        # For remote test, keep adb connection enabled.
        self._bft_fixture.SetDeviceEngaged('ADB_HOST', engage=True)
      self._polarity = self.GetCCPolarity()

    logging.info('Detect polarity: %s', self._polarity)
