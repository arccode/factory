# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""USB type-C CC line polarity check and operation flip test w/ Plankton-Raiden.

Description
-----------
This test flips the polarity bit of the USB type-C. Usually, the test will come
along with other USB type-C test, for example, CC1/CC2 USB performance
(``removable_storage.py``).

Automated test is unstable, you may have to retry. The Plankton-Raiden board
guesses the polarity bit everytime ``SetDeviceEngaged()``. Then it tries to
flip the CC polarity to the another side. We have found that we need to charge
the DUT in order to flip, and because of the charge action, the Plankton-Raiden
board guesses the logical polarity bit again (you can find that the polarity is
switching between CC1 and CC2 back-and-forth) and thus the flipping is unstable.

Test Procedure
--------------
This test can be tested manualy with the help from operator or automatically.

For normal USB type-C cable, this is a manual test with the help from operator:

1. Check USB type-C cable connected direction is right by CC polarity
2. Show operation instruction for cable flipping to test another CC line.

For double CC cable, this is an automated test:

- This test can flip CC automatically or you can set Arg
  ``double_cc_flip_target`` as 'CC1' or 'CC2' to indicate the final CC
  position.
- If test scheme can guarantee double CC cable connection is not twisted,
  that is, Plankton CC1 is connected to DUT CC1, then it can set Arg
  ``double_cc_quick_check`` as True to accelerate the test.

Dependency
----------
- For manual test, you need a normal USB type-C cable to connect with
  Plankton-Raiden board.
- For automated test, you need a double CC cable to connection with
  Plankton-Raiden board.

Examples
--------
To manual test with a dummy BFTFixture by asking operator to flip the cable,
add this in test list::

  {
    "pytest_name": "plankton_cc_flip_check",
    "args": {
      "bft_fixture": {
        "class_name":
          "cros.factory.test.fixture.dummy_bft_fixture.DummyBFTFixture",
        "params": {}
      },
      "ask_flip_operation": true,
      "usb_c_index": 0,
      "state_src_ready": "SNK_READY"
    }
  }

Automated test with a dolphin BFTFixture and flipping the polarity to CC1::

  {
    "pytest_name": "plankton_cc_flip_check",
    "args": {
      "bft_fixture": {
        "class_name":
          "cros.factory.test.fixture.dummy_bft_fixture.DummyBFTFixture",
        "params": {}
      },
      "double_cc_flip_target": "CC1",
      "usb_c_index": 1,
      "state_src_ready": "SNK_READY"
    }
  }
"""

import logging

from cros.factory.device import device_utils
from cros.factory.test import session
from cros.factory.test.fixture import bft_fixture
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils

_CC_UNCONNECT = 'UNCONNECTED'


class PlanktonCCFlipCheck(test_case.TestCase):
  """Plankton USB type-C CC line polarity check and operation flip test."""
  ARGS = [
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP),
      Arg('adb_remote_test', bool, 'Run test against remote ADB target.',
          default=False),
      Arg('usb_c_index', int, 'Index of DUT USB_C port'),
      Arg('original_enabled_cc', str, 'Set "CC1" or "CC2" if you want to check '
          'what CC pin is enabled now. There is no check if it is not set.',
          default=None),
      Arg('ask_flip_operation', bool,
          'Determine whether to ask operator to flip cable.',
          default=False),
      Arg('double_cc_flip_target', str,
          'If using double CC cable, set either "CC1" or "CC2" for the target '
          'to flip. Flip anyway if this is not set.',
          default=None),
      Arg('double_cc_quick_check', bool,
          'If using double CC cable, set True if you guarantee CC pair is not '
          'reversed. CC polarity in Plankton side implies DUT side.',
          default=False),
      Arg('timeout_secs', int,
          'Timeout seconds for operation, set 0 for operator pressing enter '
          'key to finish operation.',
          default=0),
      Arg('state_src_ready', (int, str), 'State number of pd state SRC_READY.',
          default=22),
      Arg('wait_dut_reconnect_secs', int,
          'Wait DUT to reconnect for n seconds after CC flip. This is required '
          'if remote DUT might be disconnected a while after CC flip, e.g. DUT '
          'has no battery and will reboot on CC flip. If n equals to 0, will '
          'wait forever.', default=5),
      Arg('init_cc_state_retry_times', int, 'Retry times for init CC state.',
          default=3)
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self.ui.ToggleTemplateClass('font-large', True)
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
        self._bft_fixture.SetFakeDisconnection(1)
        self.Sleep(1)
    self._polarity = self.GetCCPolarityWithRetry(
        self.args.init_cc_state_retry_times)
    logging.info('Initial polarity: %s', self._polarity)

  def GetCCPolarity(self):
    """Gets enabled CC line for USB_C port arg.usb_c_index.

    Returns:
      'CC1' or 'CC2', or _CC_UNCONNECT if it doesn't detect SRC_READY.
    """
    if not self._dut.IsReady():
      self.ui.SetState(_('Wait DUT to reconnect'))
      session.console.info(
          'Lose connection to DUT, waiting for DUT to reconnect')
      sync_utils.WaitFor(lambda: self._dut.Call(['true']) == 0,
                         self.args.wait_dut_reconnect_secs,
                         poll_interval=1)

    # For double CC cable, if we guarantee CC pair is not reversed, polarity in
    # Plankton side implies DUT side.
    if self._double_cc_quick_check:
      return self._bft_fixture.GetPDState()['polarity']

    port_status = self._dut.usb_c.GetPDStatus(self.args.usb_c_index)
    # For newer version EC, port_status[state] will return string instead of
    # state number.
    if self._adb_remote_test or self._bft_fixture.IsParallelTest():
      # For remote or parallel test, just feedback polarity.
      return port_status['polarity']
    if (port_status['state'] == self.args.state_src_ready or
        port_status['state'] == 'SRC_READY'):
      return port_status['polarity']
    logging.info('Detected port state is not state_src_ready (expect: %s '
                 'or SRC_READY, got: %s).',
                 self.args.state_src_ready, port_status['state'])
    return _CC_UNCONNECT

  def CheckCCPolarityWithRetry(self, expected_polarity, retry_times):
    """Check the CC Polarity.

    It will retry by retry_times argument to let PD do negotiate.

    Args:
      expected_polarity: expected polarity.
      retry_times: retry times.

    Returns:
      'CC1' or 'CC2', or _CC_UNCONNECT
    """
    # We may need some time for PD negotiate and settle down
    retry_times_left = retry_times
    polarity = self.GetCCPolarity()
    while retry_times_left != 0 and polarity != expected_polarity:
      self.Sleep(1)
      polarity = self.GetCCPolarity()
      logging.info('[%d]Poll polarity %s', retry_times_left, polarity)
      retry_times_left -= 1
    return polarity

  def GetCCPolarityWithRetry(self, retry_times):
    """Get the CC Polarity.

    It will retry by retry_times argument to let PD do negotiate.

    Args:
      retry_times: retry times.

    Returns:
      'CC1' or 'CC2', or _CC_UNCONNECT
    """
    # We may need some time for PD negotiate and settle down
    retry_times_left = retry_times
    polarity = self.GetCCPolarity()
    while retry_times_left != 0 and polarity == _CC_UNCONNECT:
      self.Sleep(1)
      polarity = self.GetCCPolarity()
      logging.info('[%d]Poll polarity %s', retry_times_left, polarity)
      retry_times_left -= 1
    return polarity

  def tearDown(self):
    self._bft_fixture.Disconnect()

  def runTest(self):
    if (self.args.original_enabled_cc is not None and
        self._polarity != self.args.original_enabled_cc and
        not self._bft_fixture.IsDoubleCCCable()):
      self.fail('Original polarity is wrong (expect: %s, got: %s). '
                'Does Raiden cable connect in correct direction?' %
                (self.args.original_enabled_cc, self._polarity))

    if self.args.ask_flip_operation:
      self.ui.SetState(_('Flip USB type-C cable and plug in again...'))
      if self.args.timeout_secs == 0:
        self.ui.SetState(_('And press Enter key to continue...'), append=True)
        self.ui.WaitKeysOnce(test_ui.ENTER_KEY)
        polarity = self.GetCCPolarity()
        if polarity in (self._polarity, _CC_UNCONNECT):
          self.FailTask(
              'DUT does not detect cable flipped. Was it really flipped?')
      else:
        # Start countdown timer.
        self.ui.StartFailingCountdownTimer(self.args.timeout_secs)
        while True:
          self.Sleep(0.5)
          polarity = self.GetCCPolarity()
          if polarity not in (self._polarity, _CC_UNCONNECT):
            return

    elif (self._bft_fixture.IsDoubleCCCable() and
          (not self.args.double_cc_flip_target or
           self._polarity != self.args.double_cc_flip_target)):
      if self.args.timeout_secs:
        self.ui.StartFailingCountdownTimer(self.args.timeout_secs)

      session.console.info('Double CC test, doing CC flip...')
      # TODO(yllin): Remove this if solve the plankton firmware issue
      def charge_check_flip():
        self._bft_fixture.SetDeviceEngaged('CHARGE_5V', True)
        self.Sleep(2)
        new_polarity = self.GetCCPolarityWithRetry(5)
        if new_polarity != self._polarity:
          return
        self._bft_fixture.SetMuxFlip(0)
        self.Sleep(2)

      charge_check_flip()
      if self._adb_remote_test and not self._double_cc_quick_check:
        # For remote test, keep adb connection enabled.
        self._bft_fixture.SetDeviceEngaged('ADB_HOST', engage=True)

      new_polarity = self.CheckCCPolarityWithRetry(self._polarity, 5)

      if new_polarity == self._polarity:
        self.FailTask('Unexpected polarity')
