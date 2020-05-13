# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Touch Component."""

import logging
import struct
import time

from cros.factory.device import device_types


class Touch(device_types.DeviceComponent):
  """Touch Component."""

  def GetController(self, index):
    """Gets the touch controller with specified index.

    Args:
      index: index of the touch device.

    Returns:
      The corresponding touch controller.
    """
    raise NotImplementedError


class TouchController(device_types.DeviceComponent):
  """Touch Controller."""

  def CheckInterface(self):
    """Check whether the controller interface exists or not.

    Returns:
      True if the controller interface exists. Otherwise, False.
    """
    raise NotImplementedError

  def Calibrate(self):
    """Calibrate the controller.

    Returns:
      True if the calibration is successful. Otherwise, False.
    """
    raise NotImplementedError

  def GetMatrices(self, frame_idx_list):
    """Return matrices of values for touch uniformity test.

    Args:
      frame_idx_list: A list of frame indices.

    Returns:
      A list of matrices.
    """
    raise NotImplementedError


class Atmel1664sTouchController(TouchController):
  """Atmel 1664s touch controller."""

  _I2C_DEVICES_PATH = '/sys/bus/i2c/devices'
  _KERNEL_DEBUG_PATH = '/sys/kernel/debug/atmel_mxt_ts'
  _FRAME_FILENAMES = ['refs', 'deltas']

  def __init__(self, dut, i2c_bus_id=None):
    super(Atmel1664sTouchController, self).__init__(dut)
    if i2c_bus_id is None:
      i2c_bus_id = self._ProbeI2CBusId()
    i2c_device_path = dut.path.join(self._I2C_DEVICES_PATH, i2c_bus_id)
    self._object_path = dut.path.join(i2c_device_path, 'object')
    self._kerdbg_path = dut.path.join(self._KERNEL_DEBUG_PATH, i2c_bus_id)
    self._rows = None
    self._cols = None
    if self.CheckInterface():
      size = dut.ReadSpecialFile(dut.path.join(i2c_device_path, 'matrix_size'))
      self._rows, self._cols = [int(s) for s in size.split()]

  def _ProbeI2CBusId(self):
    candidates = [
        self._device.path.basename(path)
        for path in self._device.Glob(
            self._device.path.join(self._KERNEL_DEBUG_PATH, '*'))]
    assert len(candidates) == 1, (
        'Not having exactly one possible device: %s' % candidates)
    return candidates[0]

  def CheckInterface(self):
    """See TouchController.CheckInterface."""
    return self._device.path.exists(self._object_path)

  def Calibrate(self):
    """See TouchController.Calibrate."""
    logging.info('Calibrating...')
    # Force calibration with T6 instance 0, byte 2 (calibrate), non-zero value.
    self._device.WriteFile(self._object_path, '06000201')
    # Empirical value to give the controller some time to finish calibration.
    time.sleep(0.2)
    return True  # TODO(dparker): Figure out how to detect calibration errors.

  def GetMatrices(self, frame_idx_list):
    """See TouchController.GetMatrices.

    Args:
      frame_idx_list: Index 0 = References, Index 1 = Deltas.
    """
    fmt = '<%dh' % (self._rows * self._cols)
    nbytes = struct.calcsize(fmt)

    result = []
    for frame_idx in frame_idx_list:
      file_name = self._FRAME_FILENAMES[frame_idx]
      file_path = self._device.path.join(self._kerdbg_path, file_name)
      buf = self._device.ReadSpecialFile(file_path, count=nbytes)
      data = struct.unpack(fmt, buf)
      result.append([
          list(data[i * self._cols:(i + 1) * self._cols])
          for i in range(self._rows)])
    return result
