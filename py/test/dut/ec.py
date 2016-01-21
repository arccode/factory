#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""System EC service provider.

This module provides accessing Embedded Controller (EC) on a device.
"""

from __future__ import print_function
import re

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component


class EmbeddedController(component.DUTComponent):
  """System module for embedded controller."""

  # Regular expression for parsing ectool output.
  I2C_READ_RE = re.compile(r'I2C port \d+ at \S+ offset \S+ = (0x[0-9a-f]+)')

  def _GetOutput(self, command):
    result = self._dut.CallOutput(command)
    return result.strip() if result is not None else ''

  def GetECVersion(self):
    """Gets the EC firmware version.

    Returns:
      A string of the EC firmware version.
    """
    return self._GetOutput(['mosys', 'ec', 'info', '-s', 'fw_version'])

  def GetECConsoleLog(self):
    """Gets the EC console log.

    Returns:
      A string containing EC console log.
    """
    return self._GetOutput(['ectool', 'console'])

  def GetECPanicInfo(self):
    """Gets the EC panic info.

    Returns:
      A string of EC panic info.
    """
    return self._GetOutput(['ectool', 'panicinfo'])

  def ProbeEC(self):
    """Says hello to EC.
    """
    try:
      if self._dut.CallOutput(['ectool', 'hello']).find('EC says hello') == -1:
        raise self.Error('Did not find "EC says hello".')
    except Exception as e:
      raise self.Error('Unable to say hello: %s' % e)
    return True

  def I2CRead(self, port, addr, reg):
    """Reads 16-bit value from I2C bus connected via EC.

    This function cannot access system I2C buses that are not routed via EC.

    Args:
      port: I2C port ID.
      addr: I2C slave address.
      reg: Slave register address.

    Returns:
      Integer value read from slave.
    """
    try:
      ectool_output = self._dut.CheckOutput(
          ['ectool', 'i2cread', '16', str(port), str(addr), str(reg)])
      return int(self.I2C_READ_RE.findall(ectool_output)[0], 16)
    except Exception as e:  # pylint: disable=W0703
      raise self.Error('Unable to read from I2C: %s' % e)

  def I2CWrite(self, port, addr, reg, value):
    """Writes 16-bit value to I2C bus connected via EC.

    This function cannot access system I2C buses that are not routed via EC.

    Args:
      port: I2C port ID.
      addr: I2C slave address.
      reg: Slave register address.
      value: 16-bit value to write.
    """
    try:
      self._dut.CheckCall(['ectool', 'i2cwrite', '16', str(port), str(addr),
                           str(reg), str(value)])
    except Exception as e:  # pylint: disable=W0703
      raise self.Error('Unable to write to I2C: %s' % e)

