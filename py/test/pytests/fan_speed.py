# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to ensure the functionality of CPU fan.

It provides two types of test:
A. target_rpm mode
B. spin_max_then_half mode.
For mode B, it first spins fan up to a max_rpm to get an empirical maximum
fan rpm; then it runs mode A with half of the empirical max rpm as target_rpm.

In mode A, the steps are:
1. Sets the fan speed to a target RPM.
2. Monitors the fan speed for a given period (duration_secs) with sampling
   interval (probe_interval_secs). Then it takes average of the latest
   #num_samples_to_use samples as the stablized fan speed reading.
3. Checks that the averaged reading is within range
   [target_rpm - error_margin, target_rpm + error_margin].

dargs:
  duration_secs: Duration of monitoring fan speed in seconds.
  error_margin: Fail the test if actual fan speed is off the target by the
      margin.
  max_rpm: A relatively high RPM for probing maximum fan speed. It is used
      when spin_max_then_half=True.
  num_samples_to_use: Number of lastest samples to count average as stablized
      speed.
  probe_interval_secs: Interval of probing fan speed in seconds.
  spin_max_then_half: If True, spin the fan to max_rpm, measure the empirical
      reading, and set fan speed to half of the empirical reading. Note that
      if True, target_rpm is invalid.
  target_rpm: Target RPM to set during test. Unused if spin_max_then_half
      is set.
"""

import factory_common # pylint: disable=W0611
import logging
import threading
import time
import unittest

from cros.factory import system
from cros.factory.system.board import BoardException
from cros.factory.test.args import Arg
from cros.factory.test.test_ui import MakeLabel, UI
from cros.factory.test.ui_templates import OneSection

_TEST_TITLE = MakeLabel('Fan Speed Test', zh=u'风扇转速测试')
_MSG_FAN_SPEED = MakeLabel('Fan speed (RPM):', zh=u'风扇转速(RPM):')
_ID_STATUS = 'fs_status'
_ID_RPM = 'fs_rpm'
_TEST_BODY = ('<div id="%s"></div><br>\n'
              '%s <div id="%s"></div>') % (_ID_STATUS, _MSG_FAN_SPEED, _ID_RPM)

class FanSpeedTest(unittest.TestCase):
  ARGS = [
    Arg('target_rpm', int,
        'Target RPM to set during test. Unused if spin_max_then_half is set.',
        default=0, optional=True),
    Arg('error_margin', int,
        'Fail the test if actual fan speed is off the target by the margin.',
        default=200),
    Arg('duration_secs', (int, float),
        'Duration of monitoring fan speed in seconds.', default=10),
    Arg('spin_max_then_half', bool,
        'If True, spin the fan to max_rpm, measure the actual reading, and '
        'set fan speed to half of actual max speed. Note that if True, '
        'target_rpm is invalid.',
        default=False),
    Arg('max_rpm', int,
        'A relatively high RPM for probing maximum fan speed. It is used when '
        'spin_max_then_half=True.',
        default=10000),
    Arg('probe_interval_secs', float,
        'Interval of probing fan speed in seconds.',
        default=0.2),
    Arg('num_samples_to_use', int,
        'Number of lastest samples to count average as stablized speed.',
        default=5)
  ]

  def setUp(self):
    self.assertTrue(
      self.args.target_rpm > 0 or self.args.spin_max_then_half,
      'Either set a valid target_rpm or spin_max_then_half=True.')
    self._ui = UI()
    self._template = OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._board = system.GetBoard()

  def tearDown(self):
    logging.info('Set auto fan speed control.')
    self._board.SetFanRPM(self._board.AUTO)

  def SetAndGetFanSpeed(self, target_rpm):
    """Sets fan speed and observes readings for a while (blocking call).

    Args:
      target_rpm: target fan speed.

    Returns:
      The average of the latest #num_samples_to_use samples as stablized fan
      speed reading.
    """
    observed_rpm = self._board.GetFanRPM()
    spin_up = target_rpm > observed_rpm

    status = 'Spin %s fan speed: %d -> %d RPM.' % (
      'up' if spin_up else 'down', observed_rpm, target_rpm)
    status_zh = u'风扇%s速: %d -> %d PRM.' % (
      u'加' if spin_up else u'减', observed_rpm, target_rpm)
    self._ui.SetHTML(MakeLabel(status, status_zh), id=_ID_STATUS)
    self._ui.SetHTML(observed_rpm, id=_ID_RPM)
    logging.info(status)

    self._board.SetFanRPM(int(target_rpm))
    # Probe fan speed for duration_secs seconds with sampling interval
    # probe_interval_secs.
    end_time = time.time() + self.args.duration_secs
    observed_rpms = []
    while time.time() < end_time:
      observed_rpm = self._board.GetFanRPM()
      self._ui.SetHTML(observed_rpm, id=_ID_RPM)
      observed_rpms.append(observed_rpm)
      logging.info('Observed fan RPM: %s', observed_rpm)
      time.sleep(self.args.probe_interval_secs)

    num_samples = self.args.num_samples_to_use
    total_samples = len(observed_rpms)
    if num_samples > total_samples / 2:
      logging.error('Insufficient #samples to get average fan speed. '
                    'Use latest one instead.')
      num_samples = 1
    # Average the latest #num_samples readings as stablized fan speed.
    return int(sum(observed_rpms[-num_samples:]) / num_samples)

  def Run(self):
    """Main test program running in a separate thread."""
    try:
      if self.args.spin_max_then_half:
        logging.info('Spinning fan up to to get max fan speed...')
        target_rpm = self.SetAndGetFanSpeed(self.args.max_rpm) / 2
        if target_rpm == 0:
          self._ui.Fail('Fan is not reporting any RPM')
      else:
        target_rpm = self.args.target_rpm

      observed_rpm = self.SetAndGetFanSpeed(target_rpm)
    except BoardException as e:
      self._ui.Fail('Board command failed: %s' % e)
      return

    lower_bound = target_rpm - self.args.error_margin
    upper_bound = target_rpm + self.args.error_margin
    if lower_bound <= observed_rpm <= upper_bound:
      logging.info('Observed fan RPM: %d within target range: [%d, %d].',
                   observed_rpm, lower_bound, upper_bound)
      self._ui.Pass()
    else:
      self._ui.Fail(
        'Observed fan RPM: %d out of target range: [%d, %d].' %
        (observed_rpm, lower_bound, upper_bound))

  def runTest(self):
    self._template.SetState(_TEST_BODY)
    threading.Thread(target=self.Run).start()
    self._ui.Run()
