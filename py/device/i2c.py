# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Accesses I2C devies via Linux i2c-dev driver."""

import fcntl
import io
import struct

from cros.factory.device import device_types


class I2CPeripheral(device_types.DeviceComponent):
  """Access a peripheral device on I2C bus."""

  _I2C_PERIPHERAL_FORCE = 0x0706

  def __init__(self, dut, bus, peripheral, reg_width):
    """Constructor.

    Args:
      dut: A reference to device under test. See DeviceComponent for more info.
      bus: A path to I2C bus device.
      peripheral: 7 bit I2C peripheral address.
      reg_width: Number of bits to write for register address.
    """
    super(I2CPeripheral, self).__init__(dut)
    self._bus = bus
    self._peripheral = peripheral
    self._reg_width = reg_width

  def _EncodeRegisterAddress(self, address):
    """Encodes a register address in big endian."""
    if self._reg_width == 0:
      return ''
    return struct.pack('>I', address)[-(self._reg_width // 8):]

  def WriteRead(self, write_data, read_count=None):
    """Implements hdctools wr_rd() interface.

    This function writes a list or byte values to an I2C device, then reads
    byte values from the same device.

    Args:
      write_data: A string of data to write into device.
      read_count: Nnumber of bytes to read from device.

    Returns:
      A string for data read from device, if read_count is not zero.
    """
    if not self._device.link.IsLocal():
      raise NotImplementedError('I2CBus currently supports only local targets')

    bus = io.open(self._bus, mode='r+b', buffering=0)
    fcntl.ioctl(bus.fileno(), self._I2C_PERIPHERAL_FORCE, self._peripheral)
    if write_data:
      bus.write(write_data)
    if read_count:
      return bus.read(read_count)
    return None

  def Read(self, address, count):
    """Reads data from I2C device.

    Args:
      address: Data address (register number).
      count: Number of bytes to read.

    Returns:
      A string for data read from device.
    """
    return self.WriteRead(self._EncodeRegisterAddress(address), count)

  def Write(self, address, value):
    """Writes data into I2C device.

    Args:
      address: Data address (register number).
      value: A string for data to write.
    """
    return self.WriteRead(self._EncodeRegisterAddress(address) + value)


class I2CBus(device_types.DeviceComponent):
  """Provides access to devices on I2C bus.

  Usage:
    # Declare an address using bus 0, peripheral 0x48, reg width 8 bit.
    from cros.factory.device import device_utils
    i2c = device_utils.CreateDUTInterface().i2c
    peripheral = i2c.GetPeripheral(0, 0x48, 8)
    peripheral1 = i2c.GetPeripheral('/dev/i2c-1', 0x48, 8)

    # Read 1 byte from register(0x16)
    print ord(peripheral.Read(0x16, 1))

    # Write 2 bytes register(0x20)
    peripheral.Write(0x20, '\x01\x02')

    # For more complicated I/O composition you should use struct.pack.
    peripheral.write(0x30, struct.pack('>I', myvalue))
  """

  def GetPeripheral(self, bus, peripheral, reg_width):
    """Gets an I2CPeripheral instance.

    Args:
      bus: I2C bus number, or a path to I2C bus device.
      peripheral: 7 bit I2C peripheral address, or known as "chipset address".
      reg_width: Number of bits to write for register.
    """
    if isinstance(bus, int):
      bus = '/dev/i2c-%d' % bus
    assert peripheral & (0xfe) == 0, 'I2C peripheral address has only 7 bits.'
    assert reg_width % 8 == 0, 'Register must be aligned with 8 bits.'
    assert reg_width <= 32, 'Only 0~32 bits of reg addresses are supported.'
    return I2CPeripheral(self._device, bus, peripheral, reg_width)
