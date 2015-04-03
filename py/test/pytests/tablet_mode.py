# -*- coding: utf-8 -*-
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests that certain conditions are met when in tablet mode.

Currently, the only thing checked is that the lid switch is not triggered.
"""

import asyncore
import evdev
import unittest

import factory_common  # pylint: disable=W0611

from cros.factory.test import evdev_utils
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.countdown_timer import StartCountdownTimer
from cros.factory.test.pytests.tablet_mode_ui import TabletModeUI
from cros.factory.test.utils import StartDaemonThread


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
      Arg('event_id', int, 'Event ID for evdev. None for auto probe.',
          default=None, optional=True),
      Arg('prompt_flip_notebook', bool,
          'After the test, prompt the operator to flip back into notebook '
          'mode. (This is useful to unset if the next test requires tablet '
          'mode.)',
          default=True, optional=True),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.tablet_mode_ui = TabletModeUI(self.ui,
                                       _HTML_COUNTDOWN_TIMER,
                                       _CSS_COUNTDOWN_TIMER)

    if self.args.event_id:
      self.event_dev = evdev.InputDevice('/dev/input/event%d' %
                                         self.args.event_id)
    else:
      lid_event_devices = evdev_utils.GetLidEventDevices()
      assert len(lid_event_devices) == 1, (
          'Multiple lid event devices detected')
      self.event_dev = lid_event_devices[0]
    self.tablet_mode_ui.AskForTabletMode(self.HandleConfirmTabletMode)

    # Create a thread to monitor evdev events.
    self.dispatcher = None
    StartDaemonThread(target=self.MonitorEvdevEvent)

    # Create a thread to run countdown timer.
    StartCountdownTimer(
        self.args.timeout_secs,
        lambda: self.ui.Fail('Lid switch test failed due to timeout.'),
        self.ui,
        _ID_COUNTDOWN_TIMER)

  def MonitorEvdevEvent(self):
    """Creates a process to monitor evdev event and checks for lid events."""
    self.dispatcher = evdev_utils.InputDeviceDispatcher(
        self.event_dev, self.HandleLidSwitch)
    asyncore.loop()

  def HandleLidSwitch(self, event):
    if event.type == evdev.ecodes.EV_SW and event.code == evdev.ecodes.SW_LID:
      if event.value == 0:  # LID_OPEN
        self.tablet_mode_ui.FlashFailure()
        self.ui.Fail('Lid switch was triggered unexpectedly')


  def HandleConfirmTabletMode(self, _):
    self.tablet_mode_ui.FlashSuccess()
    if self.args.prompt_flip_notebook:
      self.tablet_mode_ui.AskForNotebookMode(self.HandleConfirmNotebookMode)
    else:
      self.ui.Pass()

  def HandleConfirmNotebookMode(self, _):
    self.tablet_mode_ui.FlashSuccess()
    self.ui.Pass()

  def runTest(self):
    self.ui.Run()

  def tearDown(self):
    self.dispatcher.close()
