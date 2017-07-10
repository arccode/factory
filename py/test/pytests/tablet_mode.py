# -*- coding: utf-8 -*-
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests that certain conditions are met when in tablet mode.

Currently, the only thing checked is that the lid switch is not triggered.
"""

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
          default=_DEFAULT_TIMEOUT, optional=True),
      Arg('lid_event_id', int, 'Lid event ID for evdev. None for auto probe.',
          default=None, optional=True),
      Arg('tablet_event_id', int,
          'Tablet event ID for evdev. None for auto probe.',
          default=None, optional=True),
      Arg('prompt_flip_notebook', bool,
          'After the test, prompt the operator to flip back into notebook '
          'mode. (This is useful to unset if the next test requires tablet '
          'mode.)',
          default=True, optional=True),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.tablet_mode_ui = tablet_mode_ui.TabletModeUI(
        self.ui, _HTML_COUNTDOWN_TIMER, _CSS_COUNTDOWN_TIMER)

    self.tablet_mode_switch = False
    self.lid_event_dev = evdev_utils.FindDevice(self.args.lid_event_id,
                                                evdev_utils.IsLidEventDevice)
    try:
      self.tablet_event_dev = evdev_utils.FindDevice(
          self.args.tablet_event_id,
          evdev_utils.IsTabletEventDevice)
    except evdev_utils.DeviceNotFoundError:
      self.tablet_event_dev = None

    self.tablet_mode_ui.AskForTabletMode(self.HandleConfirmTabletMode)

    # Create a thread to monitor evdev events.
    self.lid_dispatcher = evdev_utils.InputDeviceDispatcher(
        self.lid_event_dev, self.HandleSwitchEvent)
    self.lid_dispatcher.StartDaemon()
    self.tablet_dispatcher = None
    # It is possible that a single input device can support both of SW_LID and
    # SW_TABLET_MODE therefore we can just use the first thread above to monitor
    # these two EV_SW events. Or we need this second thread.
    if self.tablet_event_dev and self.tablet_event_dev != self.lid_event_dev:
      self.tablet_dispatcher = evdev_utils.InputDeviceDispatcher(
          self.tablet_event_dev, self.HandleSwitchEvent)
      self.tablet_dispatcher.StartDaemon()

    # Create a thread to run countdown timer.
    countdown_timer.StartCountdownTimer(
        self.args.timeout_secs,
        lambda: self.ui.Fail('Lid switch test failed due to timeout.'),
        self.ui,
        _ID_COUNTDOWN_TIMER)

  def HandleSwitchEvent(self, event):
    if event.type == evdev.ecodes.EV_SW and event.code == evdev.ecodes.SW_LID:
      if event.value == 0:  # LID_OPEN
        self.tablet_mode_ui.FlashFailure()
        self.ui.Fail('Lid switch was triggered unexpectedly')

    if (event.type == evdev.ecodes.EV_SW and
        event.code == evdev.ecodes.SW_TABLET_MODE):
      self.tablet_mode_switch = event.value == 1

  def HandleConfirmTabletMode(self, _):
    if self.tablet_event_dev and not self.tablet_mode_switch:
      self.tablet_mode_ui.FlashFailure()
      self.ui.Fail("Tablet mode switch is off")
      return

    self.tablet_mode_ui.FlashSuccess()
    if self.args.prompt_flip_notebook:
      self.tablet_mode_ui.AskForNotebookMode(self.HandleConfirmNotebookMode)
    else:
      self.ui.Pass()

  def HandleConfirmNotebookMode(self, _):
    if self.tablet_event_dev and self.tablet_mode_switch:
      self.tablet_mode_ui.FlashFailure()
      self.ui.Fail('Tablet mode switch is on')
      return

    self.tablet_mode_ui.FlashSuccess()
    self.ui.Pass()

  def runTest(self):
    self.ui.Run()

  def tearDown(self):
    self.lid_dispatcher.close()
    if self.tablet_dispatcher:
      self.tablet_dispatcher.close()
