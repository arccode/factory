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

1. The test shows instruction to ask the operator to cover the sensor.
2. The test starts to wait for proximity events.
3. If the first captured event is not a ``close`` event, the test ends with
   failure.
4. The test shows instruction to ask the operator to remove the cover.
5. The test starts to wait for proximity events.
6. If the first captured event is not a ``far`` event, the test ends with
   failure.
7. If timeout reaches before all the tasks done, the test also ends with
   failure.

Dependency
----------

Examples
--------
Let's assume we want to test the sensor device ``/dev/proximity-wifi-left``,
just add a test item in the test list::

  {
    "pytest_name": "sar_proximity_sensor",
    "args": {
      "device_path": "/dev/proximity-wifi-left"
    }
  }

To provide the operator detail instructions, we can specify the messages to
show in the test list::

  {
    "pytest_name": "sar_proximity_sensor",
    "args": {
      "device_path": "/dev/proximity-wifi-left",
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

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import type_utils


IIO_GET_EVENT_FD_IOCTL = 0x80046990

PROXIMITY_EVENT_TYPE = type_utils.Enum(['close', 'far'])
PROXIMITY_EVENT_BUF_SIZE = 16


class SARProximitySensor(test_case.TestCase):
  ARGS = [
      Arg('device_path', str,
          'The device path of the sensor, usually matches the '
          'pattern ``/dev/proximity-*``.'),
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
    self.ui.ToggleTemplateClass('font-large', True)

    self._dut = device_utils.CreateDUTInterface()
    self._event_fd = None

    self._dut.CheckCall(['stop', 'powerd'])

  def runTest(self):
    self._event_fd = self._GetEventFd()

    self.ui.StartFailingCountdownTimer(self.args.timeout)

    event_type_map = {1: PROXIMITY_EVENT_TYPE.far,
                      2: PROXIMITY_EVENT_TYPE.close}

    test_flow = [(PROXIMITY_EVENT_TYPE.close, self.args.close_instruction),
                 (PROXIMITY_EVENT_TYPE.far, self.args.far_instruction)]
    for expect_event_type, instruction in test_flow:
      self.ui.SetState(instruction)

      buf = self._ReadEventBuffer()

      if buf[6] not in event_type_map:
        self.FailTask('Invalid event buffer: %r' % buf)
      got_event_type = event_type_map[buf[6]]
      if got_event_type != expect_event_type:
        self.FailTask('Expect to get a %r event, but got a %r event.' %
                      (expect_event_type, got_event_type))

  def tearDown(self):
    if self._event_fd is not None:
      try:
        os.close(self._event_fd)
      except Exception as e:
        logging.warning('Failed to close the event fd: %r', e)

    self._dut.CheckCall(['start', 'powerd'])

  def _GetEventFd(self):
    fd = os.open(self.args.device_path, 0)
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
    while True:
      try:
        fds = select.select([self._event_fd], [], [],
                            self._POLLING_TIME_INTERVAL)[0]
      except select.error as e:
        self.FailTask('Unable to read from the event fd: %r.' % e)

      if not fds:
        # make sure the user can manually stop the test
        self.Sleep(self._POLLING_TIME_INTERVAL)
        continue

      buf = [ord(x) for x in os.read(self._event_fd,
                                     PROXIMITY_EVENT_BUF_SIZE)]
      if len(buf) != PROXIMITY_EVENT_BUF_SIZE:
        self.FailTask('The event buffer has the wrong size: %r.' % len(buf))
      return buf
