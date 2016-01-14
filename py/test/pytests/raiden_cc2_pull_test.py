# -*- mode: python; coding: utf-8 -*-
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Raiden CC2 function test for Whale fixture.

Pull high C[0/1]_CC2_DUT on Whale Krill and check PD GPIO reponse to test
Raiden CC2 functionailty. Note that during pull-high test Raiden port should
be disconnected.
"""

import logging
import time
import unittest

import factory_common  # pylint: disable=W0611

from cros.factory.test import dut
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.fixture import bft_fixture

_TEST_TITLE = test_ui.MakeLabel('Raiden CC2 pull test', u'Raiden CC2 电压测试')
_DISCONNECT = lambda d: test_ui.MakeLabel(
    'Raiden port is disconnected in %.1f seconds' % d,
    u'Raiden port 失去连接 %.1f 秒' % d)
_DISCONNECT_OP = lambda d: test_ui.MakeLabel(
    'Please remove Raiden cable in %.1f seconds' % d,
    u'请在 %.1f 秒内移除 Raiden 线' % d)
_CONNECT_OP = lambda d: test_ui.MakeLabel(
    'Please attach Raiden cable in %.1f seconds' % d,
    u'请在 %.1f 秒内连接 Raiden 线' % d)
_CSS = 'body { font-size: 2em; }'


class RaidenCC2PullTest(unittest.TestCase):
  ARGS = [
      Arg('whale_bft_fixture', dict, bft_fixture.TEST_ARG_HELP),
      Arg('dolphin_bft_fixture', dict, bft_fixture.TEST_ARG_HELP),
      Arg('raiden_index', int, 'Index of DUT Raiden port'),
      Arg('disconnect_manually', bool,
          'Ask for operation to disconnect Raiden cable (just for debug usage)',
          default=False),
      Arg('disconnect_secs', int, 'Interval for Raiden port disconnection.',
          default=5)
  ]

  def setUp(self):
    self._dut = dut.Create()
    self._ui = test_ui.UI(css=_CSS)
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._raiden_index = self.args.raiden_index
    self._pull_gpio = 'C%d_CC2_DUT' % self._raiden_index

    self._whale_fixture = bft_fixture.CreateBFTFixture(
        **self.args.whale_bft_fixture)
    self._whale_fixture.SetDeviceEngaged(self._pull_gpio, engage=False)

    self._dolphin_fixture = bft_fixture.CreateBFTFixture(
        **self.args.dolphin_bft_fixture)
    self._dolphin_fixture.SetDeviceEngaged('USB3', engage=True)
    time.sleep(1)  # Wait for CC line

  def GetCCPolarity(self):
    """Gets CC status of the DUT's Raiden port.

    Port is specified by args.raiden_index.

    Returns:
      'CC1' or 'CC2'.
    """
    port_status = self._dut.usb_c.GetPDStatus(self._raiden_index)
    logging.info('Get USBPD status = %s', str(port_status))
    return port_status['polarity']

  def runTest(self):
    # Check initial CC status is 'CC1'
    cc_status = self.GetCCPolarity()
    self.assertEqual('CC1', cc_status,
                     msg='[initial stage] unexpected CC status: '
                         '%s (expect CC1)' % cc_status)

    self._whale_fixture.SetDeviceEngaged(self._pull_gpio, engage=True)

    disconnect_half_secs = float(self.args.disconnect_secs)/2
    if self.args.disconnect_manually:
      # Ask operator to manually un-plug Raiden cable
      self._template.SetState(_DISCONNECT_OP(disconnect_half_secs))
    else:
      # Use automation disconnection by Plankton-Raiden
      self._template.SetState(_DISCONNECT(self.args.disconnect_secs))
      self._dolphin_fixture.SetFakeDisconnection(self.args.disconnect_secs)

    time.sleep(disconnect_half_secs)
    # During Whale pull-high CC2 with cable disconnected, check CC is 'CC2'.
    # Measure CC status in the middle of cable disconnection interval to make
    # sure it gets stable status.
    cc_status = self.GetCCPolarity()
    self._whale_fixture.SetDeviceEngaged(self._pull_gpio, engage=False)

    if self.args.disconnect_manually:
      self._template.SetState(_CONNECT_OP(disconnect_half_secs))
    time.sleep(disconnect_half_secs)

    self.assertEqual('CC2', cc_status,
                     msg='[pull-high stage] unexpected CC status: '
                         '%s (expect CC2)' % cc_status)

    # After Whale released CC2, check CC status is 'CC1'
    time.sleep(1)  # Wait for CC line
    cc_status = self.GetCCPolarity()
    self.assertEqual('CC1', cc_status,
                     msg='[recover stage] unexpected CC status: '
                         '%s (expect CC1)' % cc_status)
