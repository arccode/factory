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
"""

import re
import subprocess
import time
import unittest

from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection
from cros.factory.test.utils import StartDaemonThread
from cros.factory.utils.process_utils import Spawn

_DEFAULT_TIMEOUT = 10

_RE_DBUS_SIGNAL = re.compile(r'^.*interface=(.*?); member=(.*?)$')
_DBUS_INTERFACE = 'org.chromium.PowerManager'
_DBUS_LID_OPENED = 'LidOpened'
_DBUS_LID_CLOSED = 'LidClosed'

_MSG_PROMPT_CLOSE = test_ui.MakeLabel(
    'Close then open the lid', u'关上接着打开上盖', 'lid-test-info')
_MSG_PROMPT_OPEN = test_ui.MakeLabel(
    'Open the lid', u'请打开上盖', 'lid-test-info')
_MSG_TIME_REMAINING = lambda t: test_ui.MakeLabel(
    'Time remaining: %d' % t, u'剩余时间：%d' % t, 'lid-test-info')

_ID_PROMPT = 'lid-test-prompt'
_ID_COUNTDOWN_TIMER = 'lid-test-timer'
_HTML_LID_SWITCH = '<div id="%s"></div>\n<div id="%s"></div>\n' % (
    _ID_PROMPT, _ID_COUNTDOWN_TIMER)

_LID_SWITCH_TEST_DEFAULT_CSS = '.lid-test-info { font-size: 2em; }'


class LidSwitchTest(unittest.TestCase):
  ARGS = [
    Arg('timeout_secs', int, 'Timeout value for the test.',
        default=_DEFAULT_TIMEOUT),
    Arg('ok_audio_path', (str, unicode),
        'Path to the OK audio file which is played after detecting lid close'
        'signal. Defaults to play ok_*.ogg in /sounds.',
        default=None, optional=True),
    Arg('audio_volume', int, 'Audio volume to use when playing OK audio file.',
        default=100)
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_LID_SWITCH_TEST_DEFAULT_CSS)
    self.template.SetState(_HTML_LID_SWITCH)
    self.ui.SetHTML(_MSG_PROMPT_CLOSE, id=_ID_PROMPT)
    self.monitor_process = None
    # Create a thread to monitor dbus events.
    StartDaemonThread(target=self.MonitorDbusSignal)
    # Create a thread to run countdown timer.
    StartDaemonThread(target=self.CountdownTimer)

  def tearDown(self):
    self.TerminateProcess()

  def MonitorDbusSignal(self):
    """Creates a process to monitor dbus signals and checks for lid events."""
    self.monitor_process = Spawn(['dbus-monitor', '--system'],
                                 stdout=subprocess.PIPE)
    while True:
      re_obj = _RE_DBUS_SIGNAL.search(self.monitor_process.stdout.readline())
      if re_obj:
        interface, member = re_obj.group(1, 2)
        if interface == _DBUS_INTERFACE:
          if member == _DBUS_LID_CLOSED:
            self.ui.SetHTML(_MSG_PROMPT_OPEN, id=_ID_PROMPT)
            self.PlayOkAudio()
          elif member == _DBUS_LID_OPENED:
            self.ui.Pass()

  def TerminateProcess(self):
    if self.monitor_process.poll() is None:
      self.monitor_process.terminate()

  def PlayOkAudio(self):
    if self.args.ok_audio_path:
      self.ui.PlayAudioFile(self.args.ok_audio_path)
    else:
      self.ui.PlayAudioFile('ok_%s.ogg' % self.ui.GetUILanguage())

  def CountdownTimer(self):
    """Starts a countdown timer and fails the test if timer reaches zero."""
    time_remaining = self.args.timeout_secs
    while time_remaining > 0:
      self.ui.SetHTML(_MSG_TIME_REMAINING(time_remaining),
                      id=_ID_COUNTDOWN_TIMER)
      time.sleep(1)
      time_remaining -= 1
    self.ui.Fail('Lid switch test failed due to timeout.')

  def runTest(self):
    self.ui.Run()
