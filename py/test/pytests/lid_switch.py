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
  use_fixture: (optional, bool) True to use fixture to perform automatic lid
      on/off test. Default False.
  lid_close: (optional) a char command to fixture MCU to close the lid.
      Default 0xC2.
  lid_open: (optional) a char command to fixture MCU to open the lid.
      Default 0xC3.
  serial_param: A parameter tuple of the target serial port:
      (port, baudrate, bytesize, parity, stopbits, timeout_secs).
      timeout_secs is used for both read and write timeout.
"""

import asyncore
import evdev
import serial
import unittest

from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.countdown_timer import StartCountdownTimer
from cros.factory.test.ui_templates import OneSection
from cros.factory.test.utils import StartDaemonThread
from cros.factory.utils import file_utils
from cros.factory.utils import serial_utils

_DEFAULT_TIMEOUT = 10
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
    Arg('use_fixture', bool,
        'True to use fixture to perform automatic lid on/off test.',
        default=False),
    Arg('lid_close', str, 'A char command to fixture MCU to close the lid.',
        default=chr(0xC2)),
    Arg('lid_open', str, 'A char command to fixture MCU to open the lid.',
        default=chr(0xC3)),
    Arg('serial_param', tuple,
        'The parameter list of a serial connection we want to use.',
        default=('/dev/ttyUSB0', 19200, serial.EIGHTBITS, serial.PARITY_NONE,
                 serial.STOPBITS_ONE , _SERIAL_TIMEOUT)),
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
    if self.args.use_fixture:
      self.ui.SetHTML(_MSG_LID_FIXTURE_CLOSE, id=_ID_PROMPT)
    else:
      self.ui.SetHTML(_MSG_PROMPT_CLOSE, id=_ID_PROMPT)

    # Prepare fixture auto test if needed.
    self.serial = None
    if self.args.use_fixture:
      try:
        self.serial = serial_utils.OpenSerial(self.args.serial_param)
      except serial.SerialException as e:
        self.ui.Fail(e)

    # Create a thread to monitor evdev events.
    self.dispatcher = None
    StartDaemonThread(target=self.MonitorEvdevEvent)
    # Create a thread to run countdown timer.
    StartCountdownTimer(
        self.args.timeout_secs,
        lambda: self.ui.Fail('Lid switch test failed due to timeout.'),
        self.ui,
        _ID_COUNTDOWN_TIMER)

    if self.args.use_fixture:
      self.CloseLid()

  def tearDown(self):
    self.TerminateLoop()
    file_utils.TryUnlink('/var/run/power_manager/lid_opened')
    if self.serial:
      self.serial.write(self.args.lid_open)
      self.serial.close()

  def ProbeLidEventSource(self):
    """Probe for lid event source."""
    for dev in map(evdev.InputDevice, evdev.list_devices()):
      for event_type, event_codes in dev.capabilities().iteritems():
        if (event_type == evdev.ecodes.EV_SW and
            evdev.ecodes.SW_LID in event_codes):
          return dev

  def HandleEvent(self, event):
    if event.type == evdev.ecodes.EV_SW and event.code == evdev.ecodes.SW_LID:
      if event.value == 1: # LID_CLOSED
        self.AskForOpenLid()
      elif event.value == 0: # LID_OPEN
        self.ui.Pass()

  def MonitorEvdevEvent(self):
    """Creates a process to monitor evdev event and checks for lid events."""
    self.dispatcher = InputDeviceDispatcher(self.event_dev, self.HandleEvent)
    asyncore.loop()

  def TerminateLoop(self):
    self.dispatcher.close()

  def _CommandFixture(self, command):
    if self.serial:
      try:
        self.serial.write(command)
        self.serial.read(1)
      except serial.SerialTimeoutException:
        self.ui.Fail('Serial write/read timeout')

  def OpenLid(self):
    self._CommandFixture(self.args.lid_open)

  def CloseLid(self):
    self._CommandFixture(self.args.lid_close)

  def AskForOpenLid(self):
    if self.args.use_fixture:
      self.ui.SetHTML(_MSG_LID_FIXTURE_OPEN, id=_ID_PROMPT)
      self.OpenLid()
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
