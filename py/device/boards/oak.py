# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.device.boards import chromeos
from cros.factory.device import device_types
from cros.factory.device import power
from cros.factory.device import usb_c


class OakUSBTypeC(usb_c.USBTypeC):
  """Board-specific usb_c class for Oak."""

  def SetHPD(self, port):
    self._CallPD(['gpioset', 'USB_DP_HPD', '1'])

  def ResetHPD(self, port):
    self._CallPD(['gpioset', 'USB_DP_HPD', '0'])


class OakPower(power.Power):
  """Board-specific power class for Oak."""

  def CheckACPresent(self):
    p = self._device.Glob('/sys/class/power_supply/CROS_USB_PD_CHARGER*/online')
    for power_path in p:
      if self._device.ReadFile(power_path).strip() == '1':
        return True
    return False


class OakBoard(chromeos.ChromeOSBoard):
  """Board interface for Oak (MT8173)."""

  @device_types.DeviceProperty
  def power(self):
    return OakPower(self)

  @device_types.DeviceProperty
  def usb_c(self):
    return OakUSBTypeC(self)
