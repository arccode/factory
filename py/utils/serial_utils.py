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
import serial

def OpenSerial(param):
  """Tries to open a serial port.

  Args:
    param: Parameter tuple for a serial connection:
        (port, baudrate, bytesize, parity, stopbits, timeout_secs).
        timeout_secs is used for both read and write timeout.

  Returns:
    serial object if successful.

  Raises:
    serial.SerialException if open failed.
  """
  ser = None
  (port, baudrate, bytesize, parity, stopbits, timeout) = param
  try:
    ser = serial.Serial(port=port, baudrate=baudrate, bytesize=bytesize,
                        parity=parity, stopbits=stopbits, timeout=timeout,
                        writeTimeout=timeout)
    ser.open()
    return ser
  except Exception as e:
    param_str = ('(port:%r, baudrate:%d, bytesize:%d, parity:%s, stopbits:%d, '
                 'timeout:%.2f)' % param)
    raise serial.SerialException(
      'Failed to open serial port: %s.\nReason: %s' % (param_str, e))


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
