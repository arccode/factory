#!/usr/bin/python -u
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for open a serial connection.

For some test cases, DUT needs to communicates with fixuture via USB-Serial
dungle. We provides FindTtyByDriver() to help finding the right
/dev/tty* path for the given driver; and OpenSerial() to open a serial port.
"""

import glob
import os
import re
from serial import Serial, SerialException


def OpenSerial(**params):
  """Tries to open a serial port.

  Args:
    params: a dict of parameters for a serial connection. Should contain
        'port'. For other parameters, like 'baudrate', 'bytesize', 'parity',
        'stopbits' and 'timeout', please refer pySerial documentation.

  Returns:
    serial object if successful.

  Raises:
    ValueError if params is invalid; otherwise, serial.SerialException.
  """
  if 'port' not in params:
    raise SerialException('Missing parameter "port".')
  try:
    ser = Serial(**params)
    ser.open()
    return ser
  except ValueError as e:
    raise ValueError(
      'Failed to open serial port. Invalid parameter: %s' % e)
  except Exception as e:
    raise SerialException(
      'Failed to open serial port with params %r. Reason: %s' % (params, e))


def FindTtyByDriver(driver_name):
  """Finds the tty terminal matched to the given driver_name.

  Args:
    driver_name: driver name for the target TTY device.

  Returns:
    /dev/tty path if driver_name is matched; None if not found.
  """
  for candidate in glob.glob('/dev/tty*'):
    driver_path = os.path.realpath('/sys/class/tty/%s/device/driver' %
                                   os.path.basename(candidate))
    # Check if driver_name exist at the tail of driver_path.
    if re.search(driver_name + '$', driver_path):
      return candidate
  return None
