# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests lid switch functionality.
"""

import asyncore
import datetime
import evdev
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.event_log import Log

from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.countdown_timer import StartCountdownTimer

# The right BFTFixture module is dynamically imported based on args.bft_fixture.
# See LidSwitchTest.setUp() for more detail.
from cros.factory.test.fixture.bft_fixture import (BFTFixture,
                                                   BFTFixtureException,
                                                   CreateBFTFixture,
                                                   TEST_ARG_HELP)

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
  """A class to monitor input events asynchronously."""
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
  """Lid switch factory test."""
  ARGS = [
    Arg('timeout_secs', int, 'Timeout value for the test.',
        default=_DEFAULT_TIMEOUT),
    Arg('ok_audio_path', (str, unicode),
        'Path to the OK audio file which is played after detecting lid close'
        'signal. Defaults to play ok_*.ogg in /sounds.',
        default=None, optional=True),
    Arg('audio_volume', int,
        'Percentage of audio volume to use when playing OK audio file.',
        default=100),
    Arg('event_id', int, 'Event ID for evdev. None for auto probe.',
        default=None, optional=True),
    Arg('bft_fixture', dict, TEST_ARG_HELP,
        default=None, optional=True),
    Arg('bft_retries', int,
        'Number of retries for BFT lid open / close.',
        default=3),
    Arg('bft_pause_secs', (int, float),
        'Pause time before issuing BFT command.',
        default=0.5),
    Arg('brightness_path', str, 'Path to control brightness level.',
        default=None, optional=True),
    Arg('brightness_when_closed', int,
        'Value to brightness when lid switch closed.',
        default=None, optional=True)
  ]

  def AdjustBrightness(self, value):
    """Adjusts the intensity by writing targeting value to sysfs.

    Args:
      value: The targeted brightness value.
    """
    with open(self.args.brightness_path, 'w') as f:
      try:
        f.write('%d' % value)
      except IOError:
        self.ui.Fail('Can not write %r into brightness. '
                     'Maybe the limit is wrong' % value)

  def GetBrightness(self):
    """Gets the brightness value from sysfs."""
    with open(self.args.brightness_path, 'r') as f:
      try:
        return int(f.read())
      except IOError:
        self.ui.Fail('Can not read brightness.')

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

    self._restore_brightness = None

    if self.fixture:
      self.BFTLid(close=True)

  def tearDown(self):
    self.TerminateLoop()
    file_utils.TryUnlink('/var/run/power_manager/lid_opened')
    if self.fixture:
      self.BFTLid(close=False, fail_test=False)
      self.fixture.Disconnect()
    Log('lid_wait_sec',
        time_to_close_sec=(self._closed_sec - self._start_waiting_sec),
        time_to_open_sec=(self._opened_sec - self._closed_sec),
        use_fixture=bool(self.fixture))

    # Restore brightness
    if self.args.brightness_path is not None:
      if self._restore_brightness is not None:
        self.AdjustBrightness(self._restore_brightness)

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

    Signals:

      lid     ---+
      switch     |
                 +-----------------------------------------------------------

      fixture ---++ ++ ++-------------------+
      lid        || || ||                   |
      status     ++ ++ ++                   +--------------------------------

      test        skip        BL_ON                  BL_OFF

    Raises:
      BFTFixtureException on fixture communication error.
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
          if self.args.brightness_path is not None:
            self._restore_brightness = self.GetBrightness()
            # Close backlight
            self.AdjustBrightness(self.args.brightness_when_closed)
      elif event.value == 0: # LID_OPEN
        self._opened_sec = self.getCurrentEpochSec()
        # Restore brightness
        if self.args.brightness_path is not None:
          self.AdjustBrightness(self._restore_brightness)
        self.ui.Pass()

  def MonitorEvdevEvent(self):
    """Creates a process to monitor evdev event and checks for lid events."""
    self.dispatcher = InputDeviceDispatcher(self.event_dev, self.HandleEvent)
    asyncore.loop()

  def TerminateLoop(self):
    self.dispatcher.close()

  def BFTLid(self, close, fail_test=True):
    """Commands BFT to close/open the lid.

    It pauses for args.bft_pause_secs seconds before sending BFT command.
    Also, it retries args.bft_retries times if BFT response is unexpected.
    It fails the test if BFT response badly after retries.

    Args:
      close: True to close the lid. Otherwise, open it.
      fail_test: True to fail the test after unsuccessful retries.
    """
    error = None
    for _ in range(self.args.bft_retries + 1):
      try:
        time.sleep(self.args.bft_pause_secs)
        self.fixture.SetDeviceEngaged(BFTFixture.Device.LID_MAGNET, close)
        break
      except BFTFixtureException as e:
        error = e
    if error is None:
      self.fixture_lid_closed = close
    elif fail_test:
      self.ui.Fail('Failed to %s the lid with %d retries. Reason: %s' % (
          'close' if close else 'open', self.args.bft_retries, error))


  def AskForOpenLid(self):
    if self.fixture:
      self.ui.SetHTML(_MSG_LID_FIXTURE_OPEN, id=_ID_PROMPT)
      self.BFTLid(close=False)
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
