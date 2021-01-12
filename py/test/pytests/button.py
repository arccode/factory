# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests button functionality.

Description
-----------
This test verifies if a button is working properly by checking if its state is
changed per given instruction.

You can specify the button in different ways using the ``button_key_name``
argument:

=================== ============================================================
Key Name            Description
=================== ============================================================
``gpio:[-]NUM``     A GPIO button. ``NUM`` indicates GPIO number, and ``+/-``
                    indicates polarity (minus for active low, otherwise active
                    high).
``crossystem:NAME`` A ``crossystem`` value (1 or 0) that can be retrieved by
                    NAME.
``ectool:NAME``     A value for ``ectool gpioget`` to fetch.
``KEYNAME``         An ``evdev`` key name that can be read from ``/dev/input``.
                    Try to find the right name by running ``evtest``.
=================== ============================================================

Test Procedure
--------------
When started, the test will prompt operator to press and release given button N
times, and fail if not finished in given timeout.

Dependency
----------
Depends on the driver of specified button source: GPIO, ``crossystem``,
``ectool``, or ``evdev`` (which also needs ``/dev/input`` and ``evtest``).

Examples
--------
To test the recovery button 1 time in 30 seconds, add this in test list::

  {
    "pytest_name": "button",
    "args": {
      "button_key_name": "crossystem:recoverysw_cur"
    }
  }

To test volume down button (using ``evdev``) 3 times in 10 seconds::

  {
    "pytest_name": "button",
    "args": {
      "timeout_secs": 10,
      "button_key_name": "KEY_VOLUMEDOWN",
      "repeat_times": 3
    }
  }
"""

import logging
import time

from cros.factory.device import device_utils
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test.fixture import bft_fixture
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test.utils import button_utils
from cros.factory.test import test_case
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils


_DEFAULT_TIMEOUT = 30


class ButtonTest(test_case.TestCase):
  """Button factory test."""
  ARGS = [
      Arg('timeout_secs', int, 'Timeout value for the test.',
          default=_DEFAULT_TIMEOUT),
      Arg('button_key_name', str, 'Button key name.'),
      Arg('device_filter', (int, str),
          'Event ID or name for evdev. None for auto probe.',
          default=None),
      Arg('repeat_times', int, 'Number of press/release cycles to test',
          default=1),
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP,
          default=None),
      Arg('bft_button_name', str, 'Button name for BFT fixture',
          default=None),
      i18n_arg_utils.I18nArg('button_name', 'The name of the button.')
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.ui.ToggleTemplateClass('font-large', True)

    self.button = button_utils.Button(self.dut, self.args.button_key_name,
                                      self.args.device_filter)

    # Timestamps of starting, pressing, and releasing
    # [started, pressed, released, pressed, released, pressed, ...]
    self._action_timestamps = [time.time()]

    if self.args.bft_fixture:
      self._fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)
    else:
      self._fixture = None

    # Group checker for Testlog.
    self.group_checker = testlog.GroupParam(
        'button_wait', ['time_to_press', 'time_to_release'])

  def tearDown(self):
    timestamps = self._action_timestamps + [float('inf')]
    for release_index in range(2, len(timestamps), 2):
      time_to_press = (timestamps[release_index - 1] -
                       timestamps[release_index - 2])
      time_to_release = (timestamps[release_index] -
                         timestamps[release_index - 1])
      event_log.Log('button_wait_sec',
                    time_to_press_sec=time_to_press,
                    time_to_release_sec=time_to_release)
      with self.group_checker:
        testlog.LogParam('time_to_press', time_to_press)
        testlog.LogParam('time_to_release', time_to_release)
    if self._fixture:
      try:
        self._fixture.SimulateButtonRelease(self.args.bft_button_name)
      except Exception:
        logging.warning('failed to release button', exc_info=True)
      try:
        self._fixture.Disconnect()
      except Exception:
        logging.warning('disconnection failure', exc_info=True)

  def _PollForCondition(self, poll_method, condition_name):
    elapsed_time = time.time() - self._action_timestamps[0]
    sync_utils.PollForCondition(
        poll_method=poll_method,
        timeout_secs=self.args.timeout_secs - elapsed_time,
        condition_name=condition_name)
    self._action_timestamps.append(time.time())

  def runTest(self):
    self.ui.StartFailingCountdownTimer(self.args.timeout_secs)

    for done in range(self.args.repeat_times):
      if self.args.repeat_times == 1:
        label = _('Press the {name} button', name=self.args.button_name)
      else:
        label = _(
            'Press the {name} button ({count}/{total})',
            name=self.args.button_name,
            count=done,
            total=self.args.repeat_times)
      self.ui.SetState(label)

      if self._fixture:
        self._fixture.SimulateButtonPress(self.args.bft_button_name, 0)

      self._PollForCondition(self.button.IsPressed, 'WaitForPress')
      self.ui.SetState(_('Release the button'))

      if self._fixture:
        self._fixture.SimulateButtonRelease(self.args.bft_button_name)

      self._PollForCondition(lambda: not self.button.IsPressed(),
                             'WaitForRelease')
