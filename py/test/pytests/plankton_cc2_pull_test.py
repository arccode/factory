# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Plankton USB type-C CC2 function test for Whale fixture.

Pull high C[0/1]_CC2_DUT on Whale Krill and check PD GPIO reponse to test
USB type-C CC2 functionailty. Note that during pull-high test USB type-C port
should be disconnected.
"""

import logging

from cros.factory.device import device_utils
from cros.factory.test.fixture import bft_fixture
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg


class PlanktonCC2PullTest(test_case.TestCase):
  ARGS = [
      Arg('whale_bft_fixture', dict, bft_fixture.TEST_ARG_HELP),
      Arg('plankton_bft_fixture', dict, bft_fixture.TEST_ARG_HELP),
      Arg('usb_c_index', int, 'Index of DUT USB type-C port'),
      Arg('disconnect_manually', bool,
          'Ask for operation to disconnect Plankton cable'
          ' (just for debug usage)',
          default=False),
      Arg('disconnect_secs', int, 'Interval for USB type-C port disconnection.',
          default=5)
  ]

  def setUp(self):
    self.ui.ToggleTemplateClass('font-large', True)
    self._dut = device_utils.CreateDUTInterface()
    self._usb_c_index = self.args.usb_c_index
    self._pull_gpio = 'C%d_CC2_DUT' % self._usb_c_index

    self._whale_fixture = bft_fixture.CreateBFTFixture(
        **self.args.whale_bft_fixture)
    self._whale_fixture.SetDeviceEngaged(self._pull_gpio, engage=False)

    self._plankton_fixture = bft_fixture.CreateBFTFixture(
        **self.args.plankton_bft_fixture)
    self._plankton_fixture.SetDeviceEngaged('USB3', engage=True)
    self.Sleep(1)  # Wait for CC line

  def GetCCPolarity(self):
    """Gets CC status of the DUT's USB type-C port.

    Port is specified by args.usb_c_index.

    Returns:
      'CC1' or 'CC2'.
    """
    port_status = self._dut.usb_c.GetPDStatus(self._usb_c_index)
    logging.info('Get USBPD status = %s', str(port_status))
    return port_status['polarity']

  def runTest(self):
    # Check initial CC status is 'CC1'
    cc_status = self.GetCCPolarity()
    self.assertEqual('CC1', cc_status,
                     msg='[initial stage] unexpected CC status: '
                         '%s (expect CC1)' % cc_status)

    self._whale_fixture.SetDeviceEngaged(self._pull_gpio, engage=True)

    disconnect_half_secs = self.args.disconnect_secs / 2
    if self.args.disconnect_manually:
      # Ask operator to manually un-plug USB type-C cable
      self.ui.SetState(
          _('Please remove USB type-C cable in {secs:.1f} seconds',
            secs=disconnect_half_secs))

    else:
      # Use automation disconnection by Plankton-Raiden
      self.ui.SetState(
          _('USB type-C port is disconnected in {secs:.1f} seconds',
            secs=self.args.disconnect_secs))
      self._plankton_fixture.SetFakeDisconnection(self.args.disconnect_secs)

    self.Sleep(disconnect_half_secs)
    # During Whale pull-high CC2 with cable disconnected, check CC is 'CC2'.
    # Measure CC status in the middle of cable disconnection interval to make
    # sure it gets stable status.
    cc_status = self.GetCCPolarity()
    self._whale_fixture.SetDeviceEngaged(self._pull_gpio, engage=False)

    if self.args.disconnect_manually:
      self.ui.SetState(
          _('Please attach USB type-C cable in {secs:.1f} seconds',
            secs=disconnect_half_secs))
    self.Sleep(disconnect_half_secs)

    self.assertEqual('CC2', cc_status,
                     msg='[pull-high stage] unexpected CC status: '
                         '%s (expect CC2)' % cc_status)

    # After Whale released CC2, check CC status is 'CC1'
    self.Sleep(1)  # Wait for CC line
    cc_status = self.GetCCPolarity()
    self.assertEqual('CC1', cc_status,
                     msg='[recover stage] unexpected CC status: '
                         '%s (expect CC1)' % cc_status)
