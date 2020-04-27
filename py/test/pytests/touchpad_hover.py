# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Touchpad Hover Test.

Description
-----------
Verifies if touchpad set `ABS_DISTANCE` to 1 when being hovered and set
`ABS_DISTANCE` to 0 when not being hovered.

For more information about `ABS_DISTANCE`, see this document::

  https://www.kernel.org/doc/Documentation/input/event-codes.txt

Some touchpad may need additional initialization before starting hover test,
for example internal calibration. This test is currently implemented with an
ability to calibrate touchpad by writing a string '1' to a special file.
This test may be revised if we see more different requests for how to initialize
before starting hover test.

If you need to calibrate touchpad before hovering test by writing a string '1'
to a special file, argument `calibration_trigger` should be set to the path of
that file. In this case, you can try to find the file in a path similar to the
one in the second example.

Test Procedure
--------------
1. DUT will automatically calibrate the touchpad in the beginning.
   Just do nothing and wait for `calibration_sleep_secs` seconds.
2. When prompted, put the hover-tool into the holder in `timeout_secs` seconds.
3. When prompted, pull out the hover-tool from the holder in `timeout_secs`
   seconds.
4. Go back to step 2, repeat for `repeat_times` times.
5. In the end, there will be a false positive check.
   Just keep the hover-tool and your hands away from the touchpad and wait for
   `false_positive_check_duration` seconds.

Dependency
----------
- Based on Linux evdev.
- Need a physical hover-tool and a holder to verify touchpad behavior on
  being hovered.
- Check with touchpad vendor if there is any initialization should be done
  before starting this test. For some touchpads, we might need to know the path
  of the calibration trigger file to trigger driver perform internal
  calibration.

Examples
--------
To check touchpad hover with default parameters without calibration, add this
in test list::

  {
    "pytest_name": "touchpad_hover"
  }

If calibration is required::

  {
    "pytest_name": "touchpad_hover",
    "args": {
      "calibration_trigger":
        "/sys/bus/i2c/drivers/xxx_i2c/i2c-xxx0000:00/calibrate"
    }
  }
"""

import contextlib
import time

from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test.utils import evdev_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils

from cros.factory.external import evdev


class TouchpadHoverTest(test_case.TestCase):
  """Touchpad Hover Test."""
  ARGS = [
      Arg('touchpad_filter', (int, str),
          'Touchpad input event id or evdev name. The test will probe for '
          'event id if it is not given.', default=None),
      Arg('calibration_trigger', str,
          'The file path of the touchpad calibration trigger. '
          'If not set, calibration step will be skipped.', default=None),
      Arg('calibration_sleep_secs', int,
          'Duration to sleep for calibration in seconds.', default=1),
      Arg('repeat_times', int, 'Number of rounds of the test.', default=2),
      Arg('timeout_secs', int,
          'Timeout to put in or pull out hover-tool in seconds.', default=3),
      Arg('false_positive_check_duration', int,
          'Duration of false positive check in seconds.', default=5)]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._touchpad = evdev_utils.FindDevice(self.args.touchpad_filter,
                                            evdev_utils.IsTouchpadDevice)

  @contextlib.contextmanager
  def WithTimer(self, timeout_secs):
    timer_disabler = self.ui.StartCountdownTimer(timeout_secs)
    yield
    timer_disabler.set()

  def _WaitForValue(self, value, timeout_secs):
    def _Condition():
      while True:
        try:
          event = self._touchpad.read_one()
        except IOError:
          event = None
        if event is None:
          return False
        if (event.timestamp() >= start_time and
            event.type == evdev.ecodes.EV_ABS and
            event.code == evdev.ecodes.ABS_DISTANCE and
            event.value == value):
          return True
    start_time = time.time()
    try:
      sync_utils.WaitFor(_Condition, timeout_secs)
    except type_utils.TimeoutError:
      return False
    return True

  def _TestForValue(self, msg, val):
    self.ui.SetState(msg)
    with self.WithTimer(self.args.timeout_secs):
      self.assertTrue(
          self._WaitForValue(val, self.args.timeout_secs), 'Timeout')

  def runTest(self):
    if self.args.calibration_trigger:
      self.ui.SetState(_('Calibrating touchpad...'))
      with self.WithTimer(self.args.calibration_sleep_secs):
        self._dut.WriteFile(self.args.calibration_trigger, '1')
        self.Sleep(self.args.calibration_sleep_secs)

    for round_index in range(self.args.repeat_times):
      progress = '(%d/%d) ' % (round_index, self.args.repeat_times)
      self._TestForValue(
          [progress, _('Please put the hover-tool into the holder.')], 1)
      self._TestForValue(
          [progress,
           _('Please pull out the hover-tool from the holder.')], 0)

    self.ui.SetState(_('Checking for false positive...'))
    with self.WithTimer(self.args.false_positive_check_duration):
      fp = self._WaitForValue(1, self.args.false_positive_check_duration)
      self.assertFalse(fp, 'False Positive Detected.')
