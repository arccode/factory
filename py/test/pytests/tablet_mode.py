# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests that certain conditions are met when in tablet mode.

Currently, it check that the lid switch is not triggered and tablet mode event
is triggered and in correct state.
"""

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test.utils import evdev_utils
from cros.factory.utils.arg_utils import Arg

from cros.factory.external import evdev


class TabletModeTest(test_case.TestCase):
  """Tablet mode factory test."""
  ARGS = [
      Arg('timeout_secs', int, 'Timeout value for the test.', default=30),
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
    self.lid_dispatcher.StartDaemon()
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
      self.tablet_dispatcher.StartDaemon()

    if self.args.prompt_flip_tablet:
      self.AddTask(self.FlipTabletMode)

    if self.args.prompt_flip_notebook:
      self.AddTask(self.FlipNotebookMode)

  def tearDown(self):
    self.lid_dispatcher.close()
    if self.tablet_dispatcher:
      self.tablet_dispatcher.close()

  def HandleSwitchEvent(self, event):
    if event.type == evdev.ecodes.EV_SW and event.code == evdev.ecodes.SW_LID:
      if event.value == 0:  # LID_OPEN
        self.ShowFailure()
        self.FailTask('Lid switch was triggered unexpectedly')

    if (event.type == evdev.ecodes.EV_SW and
        event.code == evdev.ecodes.SW_TABLET_MODE):
      self.tablet_mode_switch = event.value == 1

  def StartCountdown(self):
    self.ui.StartFailingCountdownTimer(self.args.timeout_secs)

  def SetUIImage(self, image):
    self.ui.RunJS(
        'document.getElementById("image").className = args.image;', image=image)

  def FlipTabletMode(self):
    self.SetUIImage('notebook-to-tablet')
    self.ui.SetInstruction(_('Flip the lid into tablet mode'))
    confirm_button = [
        '<button id="confirm-button" data-test-event="confirm-tablet">',
        _('Confirm tablet mode'), '</button>'
    ]
    self.ui.SetHTML(confirm_button, id='confirm')
    self.event_loop.AddEventHandler('confirm-tablet',
                                    self.HandleConfirmTabletMode)
    self.StartCountdown()
    self.WaitTaskEnd()

  def HandleConfirmTabletMode(self, event):
    del event  # Unused.

    if self.tablet_event_dev and not self.tablet_mode_switch:
      self.ShowFailure()
      self.FailTask("Tablet mode switch is off")

    self.ShowSuccess()
    self.PassTask()

  def FlipNotebookMode(self):
    self.SetUIImage('tablet-to-notebook')
    self.ui.SetInstruction(_('Open the lid back to notebook mode'))
    self.ui.SetHTML(_('Press SPACE to confirm notebook mode'), id='confirm')
    # Ask OP to press space to verify the dut is in notebook mode.
    # Set virtual_key to False since the event callback should be triggered
    # from a real key press, not from a button on screen.
    self.ui.BindKey(
        test_ui.SPACE_KEY, self.HandleConfirmNotebookMode, virtual_key=False)
    self.StartCountdown()
    self.WaitTaskEnd()

  def HandleConfirmNotebookMode(self, event):
    del event  # Unused.

    if self.tablet_event_dev and self.tablet_mode_switch:
      self.ShowFailure()
      self.FailTask('Tablet mode switch is on')

    self.ShowSuccess()
    self.PassTask()

  def _ShowStatus(self, status_label):
    self.ui.SetView('status')
    self.ui.SetHTML(status_label, id='status')
    self.Sleep(1)

  def ShowSuccess(self):
    self._ShowStatus(['<span class="success">', _('Success!'), '</span>'])

  def ShowFailure(self):
    self._ShowStatus(['<span class="failure">', _('Failure'), '</span>'])
