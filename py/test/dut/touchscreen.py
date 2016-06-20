# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Touchscreen Component."""

import logging
import time

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component


_I2C_DEVICES_PATH = '/sys/bus/i2c/devices'


class Touchscreen(component.DUTComponent):
  """Touchscreen Component."""

  def __init__(self, dut):
    super(Touchscreen, self).__init__(dut)

  def SetSubmatrixSize(self, matrix_size):
    """Specify the size of submatrix that we want to check.

    Args:
      matrix_size: a tuple of (rows, cols). Or None to check the whole matrix.
    """
    raise NotImplementedError

  def CheckController(self):
    """Check whether the controller interface exists or not.

    Returns:
      True if the controller interface exists. Otherwise, False.
    """
    raise NotImplementedError

  def CalibrateController(self):
    """Calibrate the controller.

    Returns:
      True if the calibration is successful. Otherwise, False.
    """
    raise NotImplementedError

  def GetRefValues(self):
    """Get the reference values.

    Returns:
      A 2D numeric matrix.
    """
    raise NotImplementedError

  def GetDeltaValues(self):
    """Get the delta values.

    Returns:
      A 2D numeric matrix.
    """
    raise NotImplementedError


class AtmelTouchscreen(Touchscreen):
  """Touchscreen component for Atmel 1664s touch controller."""

  def __init__(self, dut, i2c_bus_id=None):
    super(AtmelTouchscreen, self).__init__(dut)
    if i2c_bus_id is None:
      i2c_bus_id = self._ProbeI2CBusId()
    i2c_device_path = dut.path.join(_I2C_DEVICES_PATH, i2c_bus_id)
    self._object_path = dut.path.join(i2c_device_path, 'object')
    self._kernel_device_path = dut.path.join('/sys/kernel/debug/atmel_mxt_ts',
                                             i2c_bus_id)

    self._rows = None
    self._cols = None
    self._rows_enabled = None
    self._cols_enabled = None
    if self.CheckController():
      size = dut.ReadSpecialFile(dut.path.join(i2c_device_path, 'matrix_size'))
      self._rows, self._cols = [int(s) for s in size.split()]

  def _ProbeI2CBusId(self):
    result = []
    names = self._dut.Glob(self._dut.path.join(_I2C_DEVICES_PATH, '*/name'))
    for name in names:
      if self._dut.ReadSpecialFile(name).strip() == 'atmel_mxt_ts':
        result.append(name.split('/')[-2])
    assert len(result) == 1, 'Not having exactly one atmel_mxt_ts'
    return result[0]

  def SetSubmatrixSize(self, matrix_size):
    """See Touchscreen.SetSubmatrixSize."""
    if matrix_size is not None:
      self._rows_enabled, self._cols_enabled = matrix_size
      assert self._rows is None or (0 < self._rows_enabled <= self._rows)
      assert self._cols is None or (0 < self._cols_enabled <= self._cols)
    else:
      self._rows_enabled = self._rows
      self._cols_enabled = self._cols

  def CheckController(self):
    """See Touchscreen.CheckController."""
    return self._dut.path.exists(self._object_path)

  def CalibrateController(self):
    """See Touchscreen.CalibrateController."""
    logging.info('Calibrating touchscreen')
    # Force calibration with T6 instance 0, byte 2 (calibrate), non-zero value.
    self._dut.WriteFile(self._object_path, '06000201')
    # Empirical value to give the controller some time to finish calibration.
    time.sleep(0.2)
    return True  # TODO(dparker): Figure out how to detect calibration errors.

  def GetRefValues(self):
    """See Touchscreen.GetRefValues."""
    logging.info('Reading refs')
    return self._ReadRaw('refs')

  def GetDeltaValues(self):
    """See Touchscreen.GetDeltaValues."""
    logging.info('Reading deltas')
    return self._ReadRaw('deltas')

  def _ReadRaw(self, filename):
    file_path = self._dut.path.join(self._kernel_device_path, filename)
    raw_data = []
    with open(file_path, 'rb') as f:
      # Per chrome-os-partner:27424, for each row of data self.cols long read
      # from controller, we will only use the first self.cols_enabled of data
      # since the rest is garbage. And we'll only read self.rows_enabled rows
      # instead of self.rows since the rest is also garbage. Note that
      # (rows_enabled, cols_enabled) is a subset of (rows, cols).
      for _ in xrange(self._rows_enabled):
        row_data = []
        buf = f.read(2 * self._cols)
        for j in xrange(self._cols_enabled):
          val = ord(buf[2 * j]) | (ord(buf[2 * j + 1]) << 8)
          if val >= 32768:
            val -= 65536
          row_data.append(val)
        raw_data.append(row_data)
    return raw_data
