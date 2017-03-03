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
   #num_samples_to_use samples as the stabilized fan speed reading.
3. Checks that the averaged reading is within range
   [target_rpm - error_margin, target_rpm + error_margin].
"""


import logging
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import factory
from cros.factory.test.i18n import _
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg


_TEST_TITLE = i18n_test_ui.MakeI18nLabel('Fan Speed Test')
_MSG_FAN_SPEED = i18n_test_ui.MakeI18nLabel('Fan speed (RPM):')
_ID_STATUS = 'fs_status'
_ID_RPM = 'fs_rpm'
_TEST_BODY = ('<div id="%s"></div><br>\n'
              '%s <div id="%s"></div>') % (_ID_STATUS, _MSG_FAN_SPEED, _ID_RPM)


def _Average(numbers):
  # Use 0.0 as the first term to sum to make sum a floating point.
  return sum(numbers, 0.0) / len(numbers)


class FanSpeedTest(unittest.TestCase):
  """A factory test for testing system fan."""

  ARGS = [
      Arg('target_rpm', (int, list),
          'A list of target RPM to set during test.'
          'Unused if spin_max_then_half is set.',
          default=0, optional=True),
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
          default=False, optional=True),
      Arg('fan_id', int, 'The ID of fan to test, use None to test all fans.',
          default=None, optional=True)]

  def setUp(self):
    self.assertTrue(
        self.args.target_rpm > 0 or self.args.spin_max_then_half,
        'Either set a valid target_rpm or spin_max_then_half=True.')
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._template.SetState(_TEST_BODY)
    self._fan = device_utils.CreateDUTInterface().fan
    if isinstance(self.args.target_rpm, int):
      self.args.target_rpm = [self.args.target_rpm]

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

    status = (
        _('Spin up fan speed: {observed_rpm} -> {target_rpm} RPM.')
        if spin_up
        else _('Spin down fan speed: {observed_rpm} -> {target_rpm} RPM.'))
    self._ui.SetHTML(
        i18n_test_ui.MakeI18nLabel(status,
                                   observed_rpm=observed_rpm,
                                   target_rpm=target_rpm),
        id=_ID_STATUS)
    self._ui.SetHTML(str(observed_rpm), id=_ID_RPM)
    logging.info(status)

    if self.args.use_percentage:
      self._fan.SetFanRPM(int(target_rpm * 100 / self.args.max_rpm),
                          self.args.fan_id)
    else:
      self._fan.SetFanRPM(int(target_rpm), self.args.fan_id)
    # Probe fan speed for duration_secs seconds with sampling interval
    # probe_interval_secs.
    end_time = time.time() + self.args.duration_secs
    # Samples of all fan speed with sample period: probe_interval_secs.
    ith_fan_samples = [[] for unused_i in xrange(fan_count)]
    while time.time() < end_time:
      observed_rpm = self._fan.GetFanRPM(self.args.fan_id)
      for i, ith_fan_rpm in enumerate(observed_rpm):
        ith_fan_samples[i].append(ith_fan_rpm)
      self._ui.SetHTML(str(observed_rpm), id=_ID_RPM)
      logging.info('Observed fan RPM: %s', observed_rpm)
      time.sleep(self.args.probe_interval_secs)

    num_samples = self.args.num_samples_to_use
    total_samples = len(ith_fan_samples[0])
    if num_samples > total_samples / 2:
      logging.error('Insufficient #samples to get average fan speed. '
                    'Use latest one instead.')
      num_samples = 1
    # Average the latest #num_samples readings as stablized fan speed.
    average_fan_rpm = []
    for i in xrange(fan_count):
      average_fan_rpm.append(_Average(ith_fan_samples[i][-num_samples:]))
    return average_fan_rpm

  def VerifyResult(self, observed_rpm, target_rpm):
    """Verify observed rpms are in the range
      (target_rpm - error_margin, target_rpm + error_margin)

    Args:
      observed_rpm: a list of fan rpm readings.
      target_rpm: target fan speed.

    Raises:
      FactoryTestFailure if any number is not within the desired range.
    """
    lower_bound = target_rpm - self.args.error_margin
    upper_bound = target_rpm + self.args.error_margin
    error_messages = []
    for i in xrange(len(observed_rpm)):
      rpm = observed_rpm[i]
      if lower_bound <= rpm <= upper_bound:
        logging.info('Observed fan %d RPM: %d within target range: [%d, %d].',
                     i, rpm, lower_bound, upper_bound)
      else:
        error_messages.append(
            'Observed fan %d RPM: %d out of target range: [%d, %d].' %
            (i, rpm, lower_bound, upper_bound))
    if error_messages:
      raise factory.FactoryTestFailure('\n'.join(error_messages))

  def runTest(self):
    """Main test function."""
    if self.args.spin_max_then_half:
      logging.info('Spinning fan up to to get max fan speed...')
      max_rpm = self.SetAndGetFanSpeed(self.args.max_rpm)
      for i in xrange(len(max_rpm)):
        if max_rpm[i] == 0:
          raise factory.FactoryTestFailure(
              'Fan %d is not reporting any RPM' % i)
      target_rpm = _Average(max_rpm) / 2
      observed_rpm = self.SetAndGetFanSpeed(target_rpm)
      self.VerifyResult(observed_rpm, target_rpm)
    else:
      for target_rpm in self.args.target_rpm:
        observed_rpm = self.SetAndGetFanSpeed(target_rpm)
        self.VerifyResult(observed_rpm, target_rpm)
