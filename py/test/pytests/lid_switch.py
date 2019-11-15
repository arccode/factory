# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests lid switch functionality."""

import datetime
import os
import time

from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
# The right BFTFixture module is dynamically imported based on args.bft_fixture.
# See LidSwitchTest.setUp() for more detail.
from cros.factory.test.fixture import bft_fixture
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test.utils import audio_utils
from cros.factory.test.utils import evdev_utils
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils

from cros.factory.external import evdev

_DEFAULT_TIMEOUT = 30
_SERIAL_TIMEOUT = 1

_BACKLIGHT_OFF_TIMEOUT = 12
_TEST_TOLERANCE = 2
_TIMESTAMP_BL_ON = _BACKLIGHT_OFF_TIMEOUT - _TEST_TOLERANCE
_TIMESTAMP_BL_OFF = _BACKLIGHT_OFF_TIMEOUT + _TEST_TOLERANCE


class LidSwitchTest(test_case.TestCase):
  """Lid switch factory test."""
  ARGS = [
      Arg('timeout_secs', int, 'Timeout value for the test.',
          default=_DEFAULT_TIMEOUT),
      Arg('ok_audio_path', str,
          'Path to the OK audio file which is played after detecting lid close'
          'signal. Defaults to play ok_*.ogg in /sounds.',
          default=None),
      Arg('audio_volume', int,
          'Percentage of audio volume to use when playing OK audio file.',
          default=100),
      Arg('device_filter', (int, str),
          'Event ID or name for evdev. None for auto probe.',
          default=None),
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP,
          default=None),
      Arg('bft_retries', int,
          'Number of retries for BFT lid open / close.',
          default=3),
      Arg('bft_pause_secs', (int, float),
          'Pause time before issuing BFT command.',
          default=0.5),
      Arg('brightness_path', str, 'Path to control brightness level.',
          default=None),
      Arg('brightness_when_closed', int,
          'Value to brightness when lid switch closed.',
          default=None),
      Arg('check_delayed_backlight', bool, 'True to check delayed backlight.',
          default=False),
      Arg('bft_control_name', str, 'Controller name on BFT fixture to trigger '
          'Lid switch', default=bft_fixture.BFTFixture.Device.LID_MAGNET)
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
        self.FailTask('Can not write %r into brightness. '
                      'Maybe the limit is wrong' % value)

  def GetBrightness(self):
    """Gets the brightness value from sysfs."""
    with open(self.args.brightness_path, 'r') as f:
      try:
        return int(f.read())
      except IOError:
        self.FailTask('Can not read brightness.')

  def setUp(self):
    self.event_dev = evdev_utils.FindDevice(self.args.device_filter,
                                            evdev_utils.IsLidEventDevice)
    self.ui.ToggleTemplateClass('font-large', True)

    self.dispatcher = evdev_utils.InputDeviceDispatcher(
        self.event_dev, self.event_loop.CatchException(self.HandleEvent))

    # Prepare fixture auto test if needed.
    self.fixture = None
    if self.args.bft_fixture:
      self.fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)
      self.fixture_lid_closed = False

    # Variables to track the time it takes to open and close the lid
    self._start_waiting_sec = self.getCurrentEpochSec()
    self._closed_sec = 0
    self._opened_sec = 0

    self._restore_brightness = None

  def tearDown(self):
    self.dispatcher.close()
    file_utils.TryUnlink('/run/power_manager/lid_opened')
    if self.fixture:
      self.BFTLid(close=False, in_tear_down=True)
      self.fixture.Disconnect()
    event_log.Log(
        'lid_wait_sec',
        time_to_close_sec=(self._closed_sec - self._start_waiting_sec),
        time_to_open_sec=(self._opened_sec - self._closed_sec),
        use_fixture=bool(self.fixture))
    testlog.LogParam('time_to_close',
                     self._closed_sec - self._start_waiting_sec)
    testlog.LogParam('time_to_open',
                     self._opened_sec - self._closed_sec)
    testlog.LogParam('use_fixture', bool(self.fixture))

    # Restore brightness
    if self.args.brightness_path is not None:
      if self._restore_brightness is not None:
        self.AdjustBrightness(self._restore_brightness)

  def getCurrentEpochSec(self):
    """Returns the time since epoch."""

    return float(datetime.datetime.now().strftime('%s.%f'))

  def CheckDelayedBacklight(self):
    """Checks delayed backlight off.

    This function calls FailTask() on backlight turned off too early, or
    backlight did not turn off after backlight timeout period.

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
    start_time = time.time()
    timeout_time = (start_time + _TIMESTAMP_BL_OFF)
    # Ignore leading bouncing signals
    self.Sleep(_TEST_TOLERANCE)

    # Check backlight power falling edge
    while time.time() < timeout_time:
      test_time = time.time() - start_time

      backlight = self.fixture.GetSystemStatus(
          bft_fixture.BFTFixture.SystemStatus.BACKLIGHT)
      if backlight == bft_fixture.BFTFixture.Status.OFF:
        if test_time < _TIMESTAMP_BL_ON:
          self.FailTask('Backlight turned off too early.')
        return
      self.Sleep(0.5)

    self.FailTask('Backlight does not turn off.')

  def HandleEvent(self, event):
    if event.type == evdev.ecodes.EV_SW and event.code == evdev.ecodes.SW_LID:
      if event.value == 1:  # LID_CLOSED
        self._closed_sec = self.getCurrentEpochSec()
        if self.fixture:
          if self.args.check_delayed_backlight:
            self.CheckDelayedBacklight()
        self.AskForOpenLid()
        if self.args.brightness_path is not None:
          self._restore_brightness = self.GetBrightness()
          # Close backlight
          self.AdjustBrightness(self.args.brightness_when_closed)
      elif event.value == 0:  # LID_OPEN
        self._opened_sec = self.getCurrentEpochSec()
        # Restore brightness
        if self.args.brightness_path is not None:
          self.AdjustBrightness(self._restore_brightness)
        self.PassTask()

  def BFTLid(self, close, in_tear_down=False):
    """Commands BFT to close/open the lid.

    It pauses for args.bft_pause_secs seconds before sending BFT command.
    Also, it retries args.bft_retries times if BFT response is unexpected.
    It fails the test if BFT response badly after retries.

    Args:
      close: True to close the lid. Otherwise, open it.
      in_tear_down: True if we are in tearDown function.
    """
    # if we are in tearDown function, the task is over, self.Sleep will fail
    # immediately.
    sleep = time.sleep if in_tear_down else self.Sleep
    for retry in range(self.args.bft_retries + 1):
      try:
        sleep(self.args.bft_pause_secs)
        self.fixture.SetDeviceEngaged(
            self.args.bft_control_name, close)
        self.fixture_lid_closed = close
        break
      except bft_fixture.BFTFixtureException as e:
        if retry == self.args.bft_retries:
          if not in_tear_down:
            self.FailTask('Failed to %s the lid with %d retries. Reason: %s' %
                          ('close'
                           if close else 'open', self.args.bft_retries, e))

  def AskForOpenLid(self):
    if self.fixture:
      self.ui.SetState(_('Demagnetizing lid sensor'))
      self.BFTLid(close=False)
    else:
      self.ui.SetState(_('Open the lid'))
      self.PlayOkAudio()

  def PlayOkAudio(self):
    if self.args.ok_audio_path:
      self.ui.PlayAudioFile(self.args.ok_audio_path)
    else:
      self.ui.PlayAudioFile(os.path.join(self.ui.GetUILocale(), 'ok.ogg'))

  def runTest(self):
    audio_utils.CRAS().EnableOutput()
    audio_utils.CRAS().SetActiveOutputNodeVolume(self.args.audio_volume)
    if self.fixture:
      self.ui.SetState(_('Magnetizing lid sensor'))
    else:
      self.ui.SetState(_('Close then open the lid'))

    self.dispatcher.StartDaemon()
    self.ui.StartFailingCountdownTimer(
        _DEFAULT_TIMEOUT if self.fixture else self.args.timeout_secs)

    if self.fixture:
      self.BFTLid(close=True)

    self.WaitTaskEnd()
