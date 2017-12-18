# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests that certain conditions are met when in tablet mode.

Currently, the only thing checked is that the lid switch is not triggered.
"""

import threading
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.external import evdev
from cros.factory.test import countdown_timer
from cros.factory.test.pytests import tablet_mode_ui
from cros.factory.test import test_ui
from cros.factory.test.utils import evdev_utils
from cros.factory.utils.arg_utils import Arg


_DEFAULT_TIMEOUT = 30

_ID_COUNTDOWN_TIMER = 'countdown-timer'

_HTML_COUNTDOWN_TIMER = '<div id="%s" class="countdown-timer"></div>' % (
    _ID_COUNTDOWN_TIMER)

_CSS_COUNTDOWN_TIMER = """
.countdown-timer {
  position: absolute;
  bottom: .3em;
  right: .5em;
  font-size: 2em;
}
"""


class TabletModeTest(unittest.TestCase):
  """Tablet mode factory test."""
  ARGS = [
      Arg('timeout_secs', int, 'Timeout value for the test.',
          default=_DEFAULT_TIMEOUT),
      Arg('lid_filter', (int, str),
          'Lid event ID or name for evdev. None for auto probe.',
          default=None),
      Arg('tablet_filter', (int, str),
          'Tablet event ID or name for evdev. None for auto probe.',
          default=None),
      Arg('prompt_flip_tablet', bool,
          'Assume the notebook is not yet in tablet mode, and operator should '
          'first be instructed to flip it as such. (This is useful to unset if '
          'the previous test finished in tablet mode.)',
          default=False),
      Arg('prompt_flip_notebook', bool,
          'After the test, prompt the operator to flip back into notebook '
          'mode. (This is useful to unset if the next test requires tablet '
          'mode.)',
          default=False),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.tablet_mode_ui = tablet_mode_ui.TabletModeUI(
        self.ui, _HTML_COUNTDOWN_TIMER, _CSS_COUNTDOWN_TIMER)

    self.tablet_mode_switch = False
    self.lid_event_dev = evdev_utils.FindDevice(self.args.lid_filter,
                                                evdev_utils.IsLidEventDevice)
    try:
      self.tablet_event_dev = evdev_utils.FindDevice(
          self.args.tablet_filter,
          evdev_utils.IsTabletEventDevice)
    except evdev_utils.DeviceNotFoundError:
      self.tablet_event_dev = None

    self.assertTrue(
        self.args.prompt_flip_tablet or self.args.prompt_flip_notebook,
        'One of prompt_flip_tablet or prompt_flip_notebook should be true.')

    # Create a thread to monitor evdev events.
    self.lid_dispatcher = evdev_utils.InputDeviceDispatcher(
        self.lid_event_dev, self.HandleSwitchEvent)
    self.tablet_dispatcher = None
    # It is possible that a single input device can support both of SW_LID and
    # SW_TABLET_MODE therefore we can just use the first thread above to
    # monitor these two EV_SW events. Or we need this second thread. Also we
    # can't have two InputDeviceDispatcher on the same device, or one of them
    # would read fail.
    # There's a bug in the python-evdev library that InputDevice only have
    # correct __eq__ operator, but not __ne__ operator, and
    # `self.tablet_event_dev != self.lid_event_dev` always return True, so we
    # need the `not (... == ...)` here.
    if self.tablet_event_dev and not (
        self.tablet_event_dev == self.lid_event_dev):
      self.tablet_dispatcher = evdev_utils.InputDeviceDispatcher(
          self.tablet_event_dev, self.HandleSwitchEvent)

  def HandleSwitchEvent(self, event):
    if event.type == evdev.ecodes.EV_SW and event.code == evdev.ecodes.SW_LID:
      if event.value == 0:  # LID_OPEN
        self.tablet_mode_ui.FlashFailure()
        self.ui.Fail('Lid switch was triggered unexpectedly')

    if (event.type == evdev.ecodes.EV_SW and
        event.code == evdev.ecodes.SW_TABLET_MODE):
      self.tablet_mode_switch = event.value == 1

  def FlipTabletMode(self):
    event = threading.Event()
    self.tablet_mode_ui.AskForTabletMode(lambda unused_event: event.set())
    event.wait()

    if self.tablet_event_dev and not self.tablet_mode_switch:
      self.tablet_mode_ui.FlashFailure()
      self.ui.Fail("Tablet mode switch is off")
      return

    self.tablet_mode_ui.FlashSuccess()

  def FlipNotebookMode(self):
    event = threading.Event()
    self.tablet_mode_ui.AskForNotebookMode(lambda unused_event: event.set())
    event.wait()

    if self.tablet_event_dev and self.tablet_mode_switch:
      self.tablet_mode_ui.FlashFailure()
      self.ui.Fail('Tablet mode switch is on')
      return

    self.tablet_mode_ui.FlashSuccess()

  def runTest(self):
    self.ui.RunInBackground(self._runTest)
    self.ui.Run()

  def _runTest(self):
    # Create a thread to run countdown timer.
    countdown_timer.StartCountdownTimer(
        self.args.timeout_secs,
        lambda: self.ui.Fail('Lid switch test failed due to timeout.'),
        self.ui,
        _ID_COUNTDOWN_TIMER)

    self.lid_dispatcher.StartDaemon()
    if self.tablet_dispatcher:
      self.tablet_dispatcher.StartDaemon()

    if self.args.prompt_flip_tablet:
      self.FlipTabletMode()

    if self.args.prompt_flip_notebook:
      self.FlipNotebookMode()

  def tearDown(self):
    self.lid_dispatcher.close()
    if self.tablet_dispatcher:
      self.tablet_dispatcher.close()
