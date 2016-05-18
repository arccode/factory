# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Basic linux specific interface."""


# Assume most linux devices will be running POSIX os.
import posixpath

import factory_common  # pylint: disable=W0611
from cros.factory.device import accelerometer
from cros.factory.device.audio import utils as audio_utils
from cros.factory.device.board import DeviceBoard
from cros.factory.device import camera
from cros.factory.device.component import DeviceProperty
from cros.factory.device import ec
from cros.factory.device import gyroscope
from cros.factory.device import hwmon
from cros.factory.device import i2c
from cros.factory.device import info
from cros.factory.device import init
from cros.factory.device import led
from cros.factory.device import memory
from cros.factory.device import path as path_module
from cros.factory.device import partitions
from cros.factory.device import power
from cros.factory.device import status
from cros.factory.device import storage
from cros.factory.device import temp
from cros.factory.device import thermal
from cros.factory.device import toybox
from cros.factory.device import touchscreen
from cros.factory.device import udev
from cros.factory.device import usb_c
from cros.factory.device import wifi


# pylint: disable=abstract-method
class LinuxBoard(DeviceBoard):

  @DeviceProperty
  def accelerometer(self):
    return accelerometer.Accelerometer(self)

  @DeviceProperty
  def audio(self):
    # Override this property in sub-classed boards to specify different audio
    # config path if required.
    return audio_utils.CreateAudioControl(self)

  @DeviceProperty
  def camera(self):
    return camera.Camera(self)

  @DeviceProperty
  def ec(self):
    return ec.EmbeddedController(self)

  @DeviceProperty
  def gyroscope(self):
    return gyroscope.Gyroscope(self)

  @DeviceProperty
  def hwmon(self):
    return hwmon.HardwareMonitor(self)

  @DeviceProperty
  def i2c(self):
    return i2c.I2CBus(self)

  @DeviceProperty
  def info(self):
    return info.SystemInfo(self)

  @DeviceProperty
  def init(self):
    return init.FactoryInit(self)

  @DeviceProperty
  def led(self):
    return led.LED(self)

  @DeviceProperty
  def memory(self):
    return memory.LinuxMemory(self)

  @DeviceProperty
  def partitions(self):
    """Returns the partition names of system boot disk."""
    return partitions.Partitions(self)

  @DeviceProperty
  def wifi(self):
    return wifi.WiFi(self)

  @DeviceProperty
  def path(self):
    """Returns a module to handle path operations.

    If self.link.IsLocal() == True, then module posixpath is returned,
    otherwise, self._RemotePath is returned.
    If you only need to change the implementation of remote DUT, try to override
    _RemotePath.
    """
    if self.link.IsLocal():
      return posixpath
    return self._RemotePath

  @DeviceProperty
  def _RemotePath(self):
    """Returns a module to handle path operations on remote DUT.

    self.path will return this object if DUT is not local. Override this to
    change the implementation of remote DUT.
    """
    return path_module.Path(self)

  @DeviceProperty
  def power(self):
    return power.Power(self)

  @DeviceProperty
  def status(self):
    """Returns live system status (dynamic data like CPU loading)."""
    return status.SystemStatus(self)

  @DeviceProperty
  def storage(self):
    return storage.Storage(self)

  @DeviceProperty
  def temp(self):
    return temp.TemporaryFiles(self)

  @DeviceProperty
  def thermal(self):
    return thermal.ECToolThermal(self)

  @DeviceProperty
  def touchscreen(self):
    return touchscreen.Touchscreen(self)

  @DeviceProperty
  def toybox(self):
    return toybox.Toybox(self)

  @DeviceProperty
  def udev(self):
    return udev.LocalUdevMonitor(self)

  @DeviceProperty
  def usb_c(self):
    return usb_c.USBTypeC(self)
