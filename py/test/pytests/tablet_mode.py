# -*- coding: utf-8 -*-
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests that lid switch does not get triggered when tablet mode is enabled."""

import asyncore
import evdev
import time
import unittest

import factory_common  # pylint: disable=W0611

from cros.factory.test import evdev_utils
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.countdown_timer import StartCountdownTimer

from cros.factory.test.ui_templates import OneSection
from cros.factory.test.utils import StartDaemonThread


_DEFAULT_TIMEOUT = 30
_FLASH_STATUS_TIME = 1

_MSG_PROMPT_FLIP_TABLET = test_ui.MakeLabel(
    'Flip the lid into tablet mode', u'把上盖掀开一圈直到贴合下盖')
_MSG_PROMPT_FLIP_NOTEBOOK = test_ui.MakeLabel(
    'Open the lid back to notebook mode', u'把上盖掀开直到正常笔电模式')
_MSG_CONFIRM_TABLET_MODE = test_ui.MakeLabel(
    'Confirm tablet mode', u'确认平板模式')
_MSG_CONFIRM_NOTEBOOK_MODE = test_ui.MakeLabel(
    'Confirm notebook mode', u'确认笔电模式')
_MSG_STATUS_SUCCESS = test_ui.MakeLabel(
    'Success!', u'成功！')
_MSG_STATUS_FAILURE = test_ui.MakeLabel(
    'Failure', u'失败')

_ID_PROMPT = 'lid-test-prompt'
_ID_CONFIRM_BUTTON = 'confirm-button'
_ID_STATUS = 'status'
_ID_COUNTDOWN_TIMER = 'lid-test-timer'

_CLASS_IMAGE_FLIP_TABLET = 'notebook-to-tablet'
_CLASS_IMAGE_FLIP_NOTEBOOK = 'tablet-to-notebook'

_EVENT_CONFIRM_TABLET_MODE = 'confirm_tablet_mode'
_EVENT_CONFIRM_NOTEBOOK_MODE = 'confirm_notebook_mode'

_HTML_EMPTY = ''
_HTML_BUILD_CONFIRM_BUTTON = lambda button_text, test_event: (
    '<button class="confirm-button" '
    'onclick="test.sendTestEvent(\'%s\')">%s</button>' %
    (test_event, button_text))
_HTML_STATUS_SUCCESS = '<div class="success">%s</div>' % _MSG_STATUS_SUCCESS
_HTML_STATUS_FAILURE = '<div class="failure">%s</div>' % _MSG_STATUS_FAILURE
_HTML_BUILD_TEMPLATE = lambda image_class='': """
<link rel="stylesheet" type="text/css" href="tablet_mode.css">
<div class="cont %s">
  <div id="%s" class="status"></div>
  <div class="right">
    <div id="%s" class="prompt"></div>
    <div id="%s" class="button-cont"></div>
    <div id="%s" class="countdown-timer"></div>
  </div>
</div>
""" % (image_class, _ID_STATUS, _ID_PROMPT,
       _ID_CONFIRM_BUTTON, _ID_COUNTDOWN_TIMER)


class LidSwitchTest(unittest.TestCase):
  """Lid switch factory test."""
  ARGS = [
      Arg('timeout_secs', int, 'Timeout value for the test.',
          default=_DEFAULT_TIMEOUT),
      Arg('event_id', int, 'Event ID for evdev. None for auto probe.',
          default=None, optional=True),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    if self.args.event_id:
      self.event_dev = evdev.InputDevice('/dev/input/event%d' %
                                         self.args.event_id)
    else:
      lid_event_devices = evdev_utils.GetLidEventDevices()
      assert len(lid_event_devices) == 1, (
          'Multiple lid event devices detected')
      self.event_dev = lid_event_devices[0]
    self.AskForTabletMode()

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
        self.FlashStatus(_HTML_STATUS_FAILURE)
        self.ui.Fail('Lid switch was triggered unexpectedly')

  def tearDown(self):
    self.dispatcher.close()

  def AskForTabletMode(self):
    self.template.SetState(_HTML_BUILD_TEMPLATE(_CLASS_IMAGE_FLIP_TABLET))
    self.ui.SetHTML(_MSG_PROMPT_FLIP_TABLET, id=_ID_PROMPT)
    self.ui.SetHTML(_HTML_BUILD_CONFIRM_BUTTON(_MSG_CONFIRM_TABLET_MODE,
                                               _EVENT_CONFIRM_TABLET_MODE),
                    id=_ID_CONFIRM_BUTTON)
    self.ui.SetHTML(_HTML_EMPTY, id=_ID_STATUS)
    self.ui.AddEventHandler(_EVENT_CONFIRM_TABLET_MODE,
                            self.HandleConfirmTabletMode)

  def AskForNotebookMode(self):
    self.template.SetState(_HTML_BUILD_TEMPLATE(_CLASS_IMAGE_FLIP_NOTEBOOK))
    self.ui.SetHTML(_MSG_PROMPT_FLIP_NOTEBOOK, id=_ID_PROMPT)
    self.ui.SetHTML(_HTML_BUILD_CONFIRM_BUTTON(_MSG_CONFIRM_NOTEBOOK_MODE,
                                               _EVENT_CONFIRM_NOTEBOOK_MODE),
                    id=_ID_CONFIRM_BUTTON)
    self.ui.SetHTML(_HTML_EMPTY, id=_ID_STATUS)
    self.ui.AddEventHandler(_EVENT_CONFIRM_NOTEBOOK_MODE,
                            self.HandleConfirmNotebookMode)

  def HandleConfirmTabletMode(self, _):
    self.FlashStatus(_HTML_STATUS_SUCCESS)
    self.AskForNotebookMode()

  def HandleConfirmNotebookMode(self, _):
    self.FlashStatus(_HTML_STATUS_SUCCESS)
    self.ui.Pass()

  def FlashStatus(self, status_label):
    self.template.SetState(_HTML_BUILD_TEMPLATE())
    self.ui.SetHTML(_HTML_EMPTY, id=_ID_PROMPT)
    self.ui.SetHTML(_HTML_EMPTY, id=_ID_CONFIRM_BUTTON)
    self.ui.SetHTML(status_label, id=_ID_STATUS)
    time.sleep(_FLASH_STATUS_TIME)

  def runTest(self):
    self.ui.Run()
