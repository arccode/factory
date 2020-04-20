# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A test to check if the SAR proximity sensor triggers events properly.

Description
-----------
It captures the proximity events from the given sensor device
(usually ``/dev/proximity-*``) and verifies if the ``close/far`` events are
triggered properly.

Note that:

1. This test doesn't support station-based remote test yet.
2. This test stops ``powerd`` service when it is capturing the events.

Test Procedure
--------------
This test requires the operator to provide some actions.

1. The test shows instruction to ask the operator to remove the cover.
2. Wait until the sensor value is small enough.
3. The test shows instruction to ask the operator to cover the sensor.
4. The test starts to wait for proximity events.
5. If the first captured event is not a ``close`` event, the test ends with
   failure.
6. The test shows instruction to ask the operator to remove the cover.
7. The test starts to wait for proximity events.
8. If the first captured event is not a ``far`` event, the test ends with
   failure.
9. If timeout reaches before all the tasks done, the test also ends with
   failure.

Dependency
----------

Examples
--------
Let's assume we want to test the sensor device ``/dev/iio:device7``, which
``echo /sys/bus/iio/devices/iio:device7/name`` outputs sx9310, just add a test
item in the test list::

  {
    "pytest_name": "sar_proximity_sensor",
    "disable_services": [
      "powerd"
    ],
    "args": {
      "device_name": "sx9310"
    }
  }

To provide the operator detail instructions, we can specify the messages to
show in the test list::

  {
    "pytest_name": "sar_proximity_sensor",
    "disable_services": [
      "powerd"
    ],
    "args": {
      "device_name": "sx9310",
      "close_instruction": "i18n! Please cover the left edge by hand",
      "far_instruction": "i18n! Please remove the cover"
    }
  }

"""

import ctypes
import fcntl
import logging
import mmap
import os
import select

from cros.factory.device import device_utils
from cros.factory.device import sensor_utils
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import type_utils


IIO_GET_EVENT_FD_IOCTL = 0x80046990

PROXIMITY_EVENT_TYPE = type_utils.Enum(['close', 'far'])
PROXIMITY_EVENT_BUF_SIZE = 16
_DEFAULT_CALIBRATE_PATH = 'events/in_proximity0_thresh_either_en'
_DEFAULT_SENSOR_VALUE_PATH = 'in_proximity0_raw'


class SARProximitySensor(test_case.TestCase):
  ARGS = [
      Arg('device_name', str,
          'If present, the device name specifying which sensor to test. Auto'
          'detect the device if not present', default=None),
      Arg('calibrate_path', str,
          ('The path to enable testing.  '
           'Must be relative to the iio device path.'),
          default=_DEFAULT_CALIBRATE_PATH),
      Arg('enable_sensor_sleep_secs', (int, float),
          'The seconds of sleep after enabling sensor.',
          default=1),
      Arg('sensor_value_path', str,
          ('The path of the sensor value to show on the UI.  Must be relative '
           'to the iio device path.  If it is None then show nothing.'),
          default=_DEFAULT_SENSOR_VALUE_PATH),
      Arg('sensor_initial_max', int,
          ('The test will start after the sensor value lower than this value.  '
           'If it is None then do not wait.'),
          default=50),
      i18n_arg_utils.I18nArg(
          'close_instruction',
          'Message for the action to trigger the ``close`` event.',
          default=_('Please cover the sensor by hand')),
      i18n_arg_utils.I18nArg(
          'far_instruction',
          'Message for the action to trigger the ``far`` event.',
          default=_('Please un-cover the sensor')),
      Arg('timeout', int,
          'Timeout of the test.',
          default=15)
  ]

  _POLLING_TIME_INTERVAL = 0.1

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    # TODO(cyueh): Find a way to support open, close, read fd on remote DUT.
    if not self._dut.link.IsLocal():
      raise ValueError('The test does not work on remote DUT.')
    self._event_fd = None

    attr_filter = {
        self.args.calibrate_path: None,
        'name': self.args.device_name
    }
    if self.args.sensor_value_path:
      attr_filter.update({self.args.sensor_value_path: None})
    self._iio_device_path = sensor_utils.FindDevice(
        self._dut, sensor_utils.IIO_DEVICES_PATTERN, **attr_filter)
    logging.info('The iio device path: %s', self._iio_device_path)
    self._sensor_value_path = self._dut.path.join(
        self._iio_device_path,
        self.args.sensor_value_path) if self.args.sensor_value_path else None
    self.assertTrue(self.args.sensor_initial_max is None or
                    self._sensor_value_path)

  def _WriteCalibrate(self, value):
    """Enable or disable the sensor.

    Returns:
      True if we need to disable the sensor after the test.
    """
    # echo value > calibrate
    try:
      path = self._dut.path.join(self._iio_device_path,
                                 self.args.calibrate_path)
      if value == '1' and self._dut.ReadFile(path).strip() == '1':
        return False
      try:
        # self.ui is not available after StartFailingCountdownTimer timeout
        self.ui.SetHTML(self.args.far_instruction, id='sar-instruction')
        self.ui.SetHTML(_('Setting the sensor'), id='sar-value')
      except Exception:
        pass
      self._dut.WriteFile(path, value)
      self.Sleep(self.args.enable_sensor_sleep_secs)
      return True
    except Exception:
      logging.exception('_WriteCalibrate %s fails', value)
    return False

  def _GetSensorValue(self, log=True):
    """Get and log sensor value.

    Returns:
      The sensor value.
    """
    output = self._dut.ReadFile(self._sensor_value_path).strip()
    if log:
      self.ui.SetHTML(output, id='sar-value')
      logging.info('sensor value: %s', output)
    return int(output)

  def runTest(self):
    self.ui.StartFailingCountdownTimer(self.args.timeout)
    # We must enable the sensor before open the device. Otherwise the sensor may
    # create ghost event. Also if the sensor is enabled by default then we don't
    # want to disable it after the test.
    disable_after_test = self._WriteCalibrate('1')
    try:
      # Before the test, make sure the sensor is un-covered
      if self.args.sensor_initial_max is not None:
        self.ui.SetHTML(self.args.far_instruction, id='sar-instruction')
        self.ui.SetHTML(_('Setting the sensor'), id='sar-value')
        while True:
          values = [self._GetSensorValue(False) for unused_index in range(32)]
          if max(values) < self.args.sensor_initial_max:
            break
          logging.info('sensor initial values with min %s and max %s',
                       min(values), max(values))
          self.Sleep(self._POLLING_TIME_INTERVAL)

      self._event_fd = self._GetEventFd()

      event_type_map = {
          1: PROXIMITY_EVENT_TYPE.far,
          2: PROXIMITY_EVENT_TYPE.close
      }

      test_flow = [(PROXIMITY_EVENT_TYPE.close, self.args.close_instruction),
                   (PROXIMITY_EVENT_TYPE.far, self.args.far_instruction)]
      for expect_event_type, instruction in test_flow:
        self.ui.SetHTML(instruction, id='sar-instruction')

        buf = self._ReadEventBuffer()

        if buf[6] not in event_type_map:
          self.FailTask('Invalid event buffer: %r' % buf)
        got_event_type = event_type_map[buf[6]]
        if got_event_type != expect_event_type:
          self.FailTask('Expect to get a %r event, but got a %r event.' %
                        (expect_event_type, got_event_type))
        logging.info('Pass %s.', expect_event_type)
    finally:
      if disable_after_test:
        self._WriteCalibrate('0')

  def tearDown(self):
    if self._event_fd is not None:
      try:
        os.close(self._event_fd)
      except Exception as e:
        logging.warning('Failed to close the event fd: %r', e)

  def _GetEventFd(self):
    path = self._dut.path.join('/dev',
                               self._dut.path.basename(self._iio_device_path))
    fd = os.open(path, 0)
    self.assertTrue(fd >= 0, "Can't open the device, error = %d" % fd)

    # Python fcntl only allows a 32-bit input to fcntl - using 0x40 here
    # allows us to try and obtain a pointer in the low 2GB of the address space.
    mm = mmap.mmap(-1, 4096, flags=mmap.MAP_ANONYMOUS | mmap.MAP_SHARED | 0x40)
    event_fdp = ctypes.c_int.from_buffer(mm)

    ret = fcntl.ioctl(fd, IIO_GET_EVENT_FD_IOCTL, event_fdp)
    os.close(fd)
    self.assertTrue(ret >= 0, "Can't get the IIO event fd, error = %d" % ret)

    event_fd = event_fdp.value
    self.assertTrue(event_fd >= 0, "Invalid IIO event fd = %d" % event_fd)

    return event_fd

  def _ReadEventBuffer(self):
    """Poll the event fd until one event occurs.

    Returns:
      The event buffer.
    """
    while True:
      try:
        fds = select.select([self._event_fd], [], [],
                            self._POLLING_TIME_INTERVAL)[0]
      except select.error as e:
        self.FailTask('Unable to read from the event fd: %r.' % e)

      if not fds:
        if self._sensor_value_path:
          self._GetSensorValue()
        # make sure the user can manually stop the test
        self.Sleep(self._POLLING_TIME_INTERVAL)
        continue

      buf = os.read(self._event_fd, PROXIMITY_EVENT_BUF_SIZE)

      if len(buf) != PROXIMITY_EVENT_BUF_SIZE:
        self.FailTask('The event buffer has the wrong size: %r.' % len(buf))
      return buf
