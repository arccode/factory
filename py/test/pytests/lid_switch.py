# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is a factory test to check the functionality of the lid switch.

dargs:
  timeout: the test runs at most #seconds (default: 30 seconds).
  ok_audio_path: (optional) an audio file's path to notify an operator to open
      the lid.
  audio_volume: (optional) volume to play the ok audio. Default 100%.
  bft_fixture: (optional) {class_name: BFTFixture's import path + module name
                           params: a dict of params for BFTFixture's Init()}.
      Default None means no BFT fixture is used.
"""

import asyncore
import datetime
import evdev
import time
import unittest

from cros.factory.event_log import Log

from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.countdown_timer import StartCountdownTimer

# The right BFTFixture module is dynamically imported based on args.bft_fixture.
# See LidSwitchTest.setUp() for more detail.
from cros.factory.test.fixture.bft_fixture import (BFTFixture,
                                                   BFTFixtureException,
                                                   CreateBFTFixture)

from cros.factory.test.ui_templates import OneSection
from cros.factory.test.utils import StartDaemonThread
from cros.factory.utils import file_utils

_DEFAULT_TIMEOUT = 30
_SERIAL_TIMEOUT = 1

_MSG_PROMPT_CLOSE = test_ui.MakeLabel(
    'Close then open the lid', u'关上接着打开上盖', 'lid-test-info')
_MSG_PROMPT_OPEN = test_ui.MakeLabel(
    'Open the lid', u'请打开上盖', 'lid-test-info')

_MSG_LID_FIXTURE_CLOSE = test_ui.MakeLabel(
    'Magnitizing lid sensor', u'磁化上盖感应器', 'lid-test-info')
_MSG_LID_FIXTURE_OPEN = test_ui.MakeLabel(
    'Demagnitizeing lid sensor', u'消磁化上盖感应器', 'lid-test-info')

_MSG_TIME_REMAINING = lambda t: test_ui.MakeLabel(
    'Time remaining: %d' % t, u'剩余时间：%d' % t, 'lid-test-info')

_ID_PROMPT = 'lid-test-prompt'
_ID_COUNTDOWN_TIMER = 'lid-test-timer'
_HTML_LID_SWITCH = ('<div id="%s"></div>\n'
                    '<div id="%s" class="lid-test-info"></div>\n' %
                    (_ID_PROMPT, _ID_COUNTDOWN_TIMER))

_LID_SWITCH_TEST_DEFAULT_CSS = '.lid-test-info { font-size: 2em; }'

_BACKLIGHT_OFF_TIMEOUT = 12
_TEST_TOLERANCE = 2
_TIMESTAMP_BL_ON = _BACKLIGHT_OFF_TIMEOUT - _TEST_TOLERANCE
_TIMESTAMP_BL_OFF = _BACKLIGHT_OFF_TIMEOUT + _TEST_TOLERANCE


class InputDeviceDispatcher(asyncore.file_dispatcher):
  def __init__(self, device, event_handler):
    self.device = device
    self.event_handler = event_handler
    asyncore.file_dispatcher.__init__(self, device)

  def recv(self, ign=None): # pylint:disable=W0613
    return self.device.read()

  def handle_read(self):
    for event in self.recv():
      self.event_handler(event)

class LidSwitchTest(unittest.TestCase):
  ARGS = [
    Arg('timeout_secs', int, 'Timeout value for the test.',
        default=_DEFAULT_TIMEOUT),
    Arg('ok_audio_path', (str, unicode),
        'Path to the OK audio file which is played after detecting lid close'
        'signal. Defaults to play ok_*.ogg in /sounds.',
        default=None, optional=True),
    Arg('audio_volume', int, 'Audio volume to use when playing OK audio file.',
        default=100),
    Arg('event_id', int, 'Event ID for evdev. None for auto probe.',
        default=None, optional=True),
    Arg('bft_fixture', dict,
        '{class_name: BFTFixture\'s import path + module name\n'
        ' params: a dict of params for BFTFixture\'s Init()}.\n'
        'Default None means no BFT fixture is used.',
        default=None, optional=True),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    if self.args.event_id:
      self.event_dev = evdev.InputDevice('/dev/input/event%d' %
                                         self.args.event_id)
    else:
      self.event_dev = self.ProbeLidEventSource()
    self.ui.AppendCSS(_LID_SWITCH_TEST_DEFAULT_CSS)
    self.template.SetState(_HTML_LID_SWITCH)

    # Prepare fixture auto test if needed.
    self.fixture = None
    if self.args.bft_fixture:
      self.fixture = CreateBFTFixture(**self.args.bft_fixture)

    if self.fixture:
      self.ui.SetHTML(_MSG_LID_FIXTURE_CLOSE, id=_ID_PROMPT)
      self.fixture_lid_closed = False
    else:
      self.ui.SetHTML(_MSG_PROMPT_CLOSE, id=_ID_PROMPT)


    # Create a thread to monitor evdev events.
    self.dispatcher = None
    StartDaemonThread(target=self.MonitorEvdevEvent)
    # Create a thread to run countdown timer.
    StartCountdownTimer(
        _DEFAULT_TIMEOUT if self.fixture else self.args.timeout_secs,
        lambda: self.ui.Fail('Lid switch test failed due to timeout.'),
        self.ui,
        _ID_COUNTDOWN_TIMER)

    # Variables to track the time it takes to open and close the lid
    self._start_waiting_sec = self.getCurrentEpochSec()
    self._closed_sec = 0
    self._opened_sec = 0

    if self.fixture:
      try:
        self.fixture.SetDeviceEngaged(BFTFixture.Device.LID_MAGNET, True)
        self.fixture_lid_closed = True
      except BFTFixtureException as e:
        self.ui.Fail(e)

  def tearDown(self):
    self.TerminateLoop()
    file_utils.TryUnlink('/var/run/power_manager/lid_opened')
    if self.fixture:
      if self.fixture_lid_closed:
        self.fixture.SetDeviceEngaged(BFTFixture.Device.LID_MAGNET, False)
      self.fixture.Disconnect()
    Log('lid_wait_sec',
        time_to_close_sec=(self._closed_sec - self._start_waiting_sec),
        time_to_open_sec=(self._opened_sec - self._closed_sec),
        use_fixture=bool(self.fixture))

  def getCurrentEpochSec(self):
    '''Returns the time since epoch.'''

    return float(datetime.datetime.now().strftime("%s.%f"))

  def ProbeLidEventSource(self):
    """Probe for lid event source."""
    for dev in map(evdev.InputDevice, evdev.list_devices()):
      for event_type, event_codes in dev.capabilities().iteritems():
        if (event_type == evdev.ecodes.EV_SW and
            evdev.ecodes.SW_LID in event_codes):
          return dev

  def CheckDelayedBacklight(self):
    """Checks delayed backlight off.

    This function calls ui.Fail() on backlight turned off too early, or
    backlight did not turn off after backlight timeout period. When backlight
    delayed off works as expected, it calls OpenLid() to test lid_open event.

    Raises: BFTFixtureException on fixture communication error.

    Signals:

      lid     ---+
      switch     |
                 +-----------------------------------------------------------

      fixture ---++ ++ ++-------------------+
      lid        || || ||                   |
      status     ++ ++ ++                   +--------------------------------

      test        skip        BL_ON                  BL_OFF

    """
    try:
      start_time = time.time()
      timeout_time = (start_time + _TIMESTAMP_BL_OFF)
      # Ignore leading bouncing signals
      time.sleep(_TEST_TOLERANCE)

      # Check backlight power falling edge
      while timeout_time > time.time():
        test_time = time.time() - start_time

        backlight = self.fixture.GetSystemStatus(
            BFTFixture.SystemStatus.BACKLIGHT)
        if backlight == BFTFixture.Status.OFF:
          if test_time >= _TIMESTAMP_BL_ON:
            # Test passed, continue to check lid open
            self.AskForOpenLid()
          else:
            self.ui.Fail('Backlight turned off too early.')
          return
        time.sleep(0.5)

      self.ui.Fail('Backlight does not turn off.')
    except Exception as e:
      self.ui.Fail(e)

  def HandleEvent(self, event):
    if event.type == evdev.ecodes.EV_SW and event.code == evdev.ecodes.SW_LID:
      if event.value == 1: # LID_CLOSED
        self._closed_sec = self.getCurrentEpochSec()
        if self.fixture:
          self.CheckDelayedBacklight()
        else:
          self.AskForOpenLid()
      elif event.value == 0: # LID_OPEN
        self._opened_sec = self.getCurrentEpochSec()
        self.ui.Pass()

  def MonitorEvdevEvent(self):
    """Creates a process to monitor evdev event and checks for lid events."""
    self.dispatcher = InputDeviceDispatcher(self.event_dev, self.HandleEvent)
    asyncore.loop()

  def TerminateLoop(self):
    self.dispatcher.close()

  def AskForOpenLid(self):
    if self.fixture:
      self.ui.SetHTML(_MSG_LID_FIXTURE_OPEN, id=_ID_PROMPT)
      try:
        self.fixture.SetDeviceEngaged(BFTFixture.Device.LID_MAGNET, False)
        self.fixture_lid_closed = False
      except BFTFixtureException as e:
        self.ui.Fail(e)
    else:
      self.ui.SetHTML(_MSG_PROMPT_OPEN, id=_ID_PROMPT)
      self.PlayOkAudio()

  def PlayOkAudio(self):
    if self.args.ok_audio_path:
      self.ui.PlayAudioFile(self.args.ok_audio_path)
    else:
      self.ui.PlayAudioFile('ok_%s.ogg' % self.ui.GetUILanguage())

  def runTest(self):
    self.ui.Run()
