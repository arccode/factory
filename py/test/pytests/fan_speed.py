# Copyright 2012 The Chromium OS Authors. All rights reserved.
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
   #num_samples_to_use samples as the stabilized fan speed reading.
3. Checks that the averaged reading is within range
   [target_rpm - error_margin, target_rpm + error_margin].
"""

import logging
import time

from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg


def _Average(numbers):
  return sum(numbers, 0) / len(numbers)


class FanSpeedTest(test_case.TestCase):
  """A factory test for testing system fan."""

  ARGS = [
      Arg('target_rpm', (int, list),
          'A list of target RPM to set during test.'
          'Unused if spin_max_then_half is set.',
          default=0),
      Arg('error_margin', int,
          'Fail the test if actual fan speed is off the target by the margin.',
          default=200),
      Arg('duration_secs', (int, float),
          'Duration of monitoring fan speed in seconds.', default=10),
      Arg('spin_max_then_half', bool,
          'If True, spin the fan to max_rpm, measure the actual reading, and '
          'set fan speed to half of actual max speed. Note that if True, '
          'target_rpm is invalid.', default=False),
      Arg('max_rpm', int,
          'A relatively high RPM for probing maximum fan speed. It is used '
          'when spin_max_then_half=True.', default=10000),
      Arg('probe_interval_secs', float,
          'Interval of probing fan speed in seconds.', default=0.2),
      Arg('num_samples_to_use', int,
          'Number of lastest samples to count average as stablized speed.',
          default=5),
      Arg('use_percentage', bool, 'Use percentage to set fan speed',
          default=False),
      Arg('fan_id', int, 'The ID of fan to test, use None to test all fans.',
          default=None)
  ]

  def setUp(self):
    if isinstance(self.args.target_rpm, int):
      self.args.target_rpm = [self.args.target_rpm]
    self.assertTrue(
        self.args.spin_max_then_half or min(self.args.target_rpm) > 0,
        'Either set a valid target_rpm or spin_max_then_half=True.')
    self._fan = device_utils.CreateDUTInterface().fan

  def tearDown(self):
    logging.info('Set auto fan speed control.')
    self._fan.SetFanRPM(self._fan.AUTO, self.args.fan_id)

  def SetAndGetFanSpeed(self, target_rpm):
    """Sets fan speed and observes readings for a while (blocking call).

    Args:
      target_rpm: target fan speed.

    Returns:
      List of fan speed, each fan speed if the average of the latest
      #num_samples_to_use samples as stabilized fan speed reading.
    """
    observed_rpm = self._fan.GetFanRPM(self.args.fan_id)
    fan_count = len(observed_rpm)
    spin_up = target_rpm > _Average(observed_rpm)

    status = _(
        '{fan_spin_direction}: {observed_rpm} -> {target_rpm} RPM.',
        fan_spin_direction=_('Spin up fan') if spin_up else _('Spin down fan'),
        observed_rpm=observed_rpm,
        target_rpm=target_rpm)

    self.ui.SetHTML(status, id='fs-status')
    self.ui.SetHTML(str(observed_rpm), id='fs-rpm')

    if self.args.use_percentage:
      self._fan.SetFanRPM(int(target_rpm * 100 / self.args.max_rpm),
                          self.args.fan_id)
    else:
      self._fan.SetFanRPM(int(target_rpm), self.args.fan_id)

    # Probe fan speed for duration_secs seconds with sampling interval
    # probe_interval_secs.
    end_time = time.time() + self.args.duration_secs
    # Samples of all fan speed with sample period: probe_interval_secs.
    ith_fan_samples = [[] for unused_i in range(fan_count)]
    while time.time() < end_time:
      observed_rpm = self._fan.GetFanRPM(self.args.fan_id)
      for i, ith_fan_rpm in enumerate(observed_rpm):
        ith_fan_samples[i].append(ith_fan_rpm)
      self.ui.SetHTML(str(observed_rpm), id='fs-rpm')
      logging.info('Observed fan RPM: %s', observed_rpm)
      self.Sleep(self.args.probe_interval_secs)

    num_samples = self.args.num_samples_to_use
    total_samples = len(ith_fan_samples[0])
    if num_samples > total_samples // 2:
      logging.error('Insufficient #samples to get average fan speed. '
                    'Use latest one instead.')
      num_samples = 1
    # Average the latest #num_samples readings as stabilized fan speed.
    return [_Average(samples[-num_samples:]) for samples in ith_fan_samples]

  def VerifyResult(self, observed_rpm, target_rpm):
    """Verify observed rpms are in the range
      (target_rpm - error_margin, target_rpm + error_margin)

    Args:
      observed_rpm: a list of fan rpm readings.
      target_rpm: target fan speed.
    """
    lower_bound = target_rpm - self.args.error_margin
    upper_bound = target_rpm + self.args.error_margin
    error_messages = []
    for i, rpm in enumerate(observed_rpm):
      if lower_bound <= rpm <= upper_bound:
        logging.info('Observed fan %d RPM: %d within target range: [%d, %d].',
                     i, rpm, lower_bound, upper_bound)
      else:
        error_messages.append(
            'Observed fan %d RPM: %d out of target range: [%d, %d].' %
            (i, rpm, lower_bound, upper_bound))
    if error_messages:
      self.FailTask('\n'.join(error_messages))

  def runTest(self):
    """Main test function."""
    if self.args.spin_max_then_half:
      logging.info('Spinning fan up to get max fan speed...')
      max_rpm = self.SetAndGetFanSpeed(self.args.max_rpm)
      for i, rpm in enumerate(max_rpm):
        if rpm == 0:
          self.FailTask('Fan %d is not reporting any RPM' % i)
      target_rpm = _Average(max_rpm) / 2
      observed_rpm = self.SetAndGetFanSpeed(target_rpm)
      self.VerifyResult(observed_rpm, target_rpm)
    else:
      for target_rpm in self.args.target_rpm:
        observed_rpm = self.SetAndGetFanSpeed(target_rpm)
        self.VerifyResult(observed_rpm, target_rpm)
