# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A class to control Ginkgo USB-GPIO adapters.

A Ginkgo USB-GPIO adapter could be used to communicate between PC USB bus and
GPIO interface. It could be configured as GPIO/I2C/SPI/CAN. This is an ideal
device if all you need is simple GPIOs while Arduino or Beaglebone is an
overkill.

Refer to the following web site for its user manual:
http://www.viewtool.com/index.php?option=com_content&view=article&id=212:driver-down&catid=39:softdownload&Itemid=18&lang=en
"""


from ctypes import byref
from ctypes import c_int
from ctypes import c_ubyte
from ctypes import c_ushort
from ctypes import cdll
import os


GPIO_DIRECTION_IN = 'in'
GPIO_DIRECTION_OUT = 'out'

GPIO_LOW = 0
GPIO_HIGH = 1


class UsbGpioError(Exception):
  pass


class UsbGpioGinkgo:
  """A USB to GPIO control device class.

  It is possible to connect multiple Ginkgo adapters to a single host by
  assigning a proper device index.
  """
  # Definition of legal GPIO port range
  MIN_GPIO_PORT = 0
  MAX_GPIO_PORT = 15

  # Definition of device types
  VGI_USBGPIO = 1
  VII_USBI2C = 1
  VAI_USBADC = 1
  VSI_USBSPI = 2
  VPI_USBPWM = 2
  VCI_USBCAN1 = 3
  VCI_USBCAN2 = 4

  # Error code
  ERR_SUCCESS = 0

  # Ginkgo driver
  GINGKO_DRIVER = 'libGinkgo_Driver.so'

  def __init__(self, device_index=0):
    self.device_index = device_index
    self._LoadDriver()

    # Scan the device
    need_init = 1
    ret = self.ginkgo_lib.VGI_ScanDevice(c_ubyte(need_init))
    if ret <= 0:
      raise UsbGpioError('scan device error!')

    # Open the device
    reserved = 0
    ret = self.ginkgo_lib.VGI_OpenDevice(c_int(self.VGI_USBGPIO),
                                         c_int(self.device_index),
                                         c_int(reserved))
    if ret != self.ERR_SUCCESS:
      raise UsbGpioError('open device error!')

  def _LoadDriver(self):
    """Load the Ginkgo driver."""
    # Try to locate the path of the ginkgo driver from possible paths.
    ld_library_paths = os.environ.get('LD_LIBRARY_PATH', '').split(':')
    lib_paths = ['/usr/local/lib64', '/usr/lib64', '/usr/local/lib', '/usr/lib']
    all_lib_paths = ld_library_paths + lib_paths
    for path in all_lib_paths:
      ginkgo_lib_path = os.path.join(path, self.GINGKO_DRIVER)
      if os.path.isfile(ginkgo_lib_path):
        break
    else:
      raise UsbGpioError('Cannot find %s in %s.' %
                         (self.GINGKO_DRIVER, all_lib_paths))

    # Try to load the driver.
    # ginkgo_lib_path = '/usr/lib64/libGinkgo_Driver.so'
    try:
      self.ginkgo_lib = cdll.LoadLibrary(ginkgo_lib_path)
    except Exception as e:
      raise UsbGpioError('load %s (%s)' % (ginkgo_lib_path, e))

  def _GetGPIOPin(self, gpio_port):
    """Convert the GPIO port number to the physical GPIO pin number."""
    # Check the validity of the gpio_port.
    if gpio_port < self.MIN_GPIO_PORT or gpio_port > self.MAX_GPIO_PORT:
      raise UsbGpioError('invalid gpio port %d' % gpio_port)
    gpio_pin = 1 << gpio_port
    return gpio_pin

  def SetDirection(self, gpio_port, direction):
    """Set the direction of the GPIO port."""
    gpio_pin = self._GetGPIOPin(gpio_port)
    if direction == 'in':
      ret = self.ginkgo_lib.VGI_SetInput(c_int(self.VGI_USBGPIO),
                                         c_int(self.device_index),
                                         c_ushort(gpio_pin))
    elif direction == 'out':
      ret = self.ginkgo_lib.VGI_SetOutput(c_int(self.VGI_USBGPIO),
                                          c_int(self.device_index),
                                          c_ushort(gpio_pin))
    else:
      raise UsbGpioError('invalid direction %s' % direction)
    if ret != self.ERR_SUCCESS:
      raise UsbGpioError('set gpio_%d to %s' % (gpio_port, direction))

  def WriteValue(self, gpio_port, value):
    """Write the value to the GPIO port."""
    gpio_pin = self._GetGPIOPin(gpio_port)
    if value == GPIO_HIGH:
      ret = self.ginkgo_lib.VGI_SetPins(c_int(self.VGI_USBGPIO),
                                        c_int(self.device_index),
                                        c_ushort(gpio_pin))
    elif value == GPIO_LOW:
      ret = self.ginkgo_lib.VGI_ResetPins(c_int(self.VGI_USBGPIO),
                                          c_int(self.device_index),
                                          c_ushort(gpio_pin))
    else:
      raise UsbGpioError('WriteValue: invalid value: %d' % value)
    if ret != self.ERR_SUCCESS:
      raise UsbGpioError('set gpio_%d to %d' % (gpio_port, value))

  def ReadValue(self, gpio_port):
    """Read the value of the GPIO port."""
    gpio_pin = self._GetGPIOPin(gpio_port)
    pin_value = c_ushort(0)
    ret = self.ginkgo_lib.VGI_ReadDatas(c_int(self.VGI_USBGPIO),
                                        c_int(self.device_index),
                                        c_ushort(gpio_pin),
                                        byref(pin_value))
    if ret != self.ERR_SUCCESS:
      raise UsbGpioError('read gpio_%d' % gpio_port)
    return GPIO_HIGH if (pin_value.value & gpio_pin) != 0 else GPIO_LOW

  def Close(self):
    """Close the device."""
    ret = self.ginkgo_lib.VGI_CloseDevice(c_int(self.VGI_USBGPIO),
                                          c_int(self.device_index))
    if ret != self.ERR_SUCCESS:
      raise UsbGpioError('close device')
