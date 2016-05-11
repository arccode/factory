# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Basic linux specific interface."""


# Assume most linux DUTs will be running POSIX os.
import posixpath

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import accelerometer
from cros.factory.test.dut.audio import utils as audio_utils
from cros.factory.test.dut import camera
from cros.factory.test.dut import ec
from cros.factory.test.dut import gyroscope
from cros.factory.test.dut import i2c
from cros.factory.test.dut import info
from cros.factory.test.dut import init
from cros.factory.test.dut import led
from cros.factory.test.dut import memory
from cros.factory.test.dut import path as path_module
from cros.factory.test.dut import partitions
from cros.factory.test.dut import power
from cros.factory.test.dut import status
from cros.factory.test.dut import storage
from cros.factory.test.dut import temp
from cros.factory.test.dut import thermal
from cros.factory.test.dut import toybox
from cros.factory.test.dut import udev
from cros.factory.test.dut import usb_c
from cros.factory.test.dut import vpd
from cros.factory.test.dut import wifi
from cros.factory.test.dut.board import (DUTBoard,
                                         DUTProperty)


# pylint: disable=abstract-method
class LinuxBoard(DUTBoard):

  @DUTProperty
  def accelerometer(self):
    return accelerometer.Accelerometer(self)

  @DUTProperty
  def audio(self):
    # Override this property in sub-classed boards to specify different audio
    # config path if required.
    return audio_utils.CreateAudioControl(self)

  @DUTProperty
  def camera(self):
    return camera.Camera(self)

  @DUTProperty
  def ec(self):
    return ec.EmbeddedController(self)

  @DUTProperty
  def gyroscope(self):
    return gyroscope.Gyroscope(self)

  @DUTProperty
  def i2c(self):
    return i2c.I2CBus(self)

  @DUTProperty
  def info(self):
    return info.SystemInfo(self)

  @DUTProperty
  def init(self):
    return init.FactoryInit(self)

  @DUTProperty
  def led(self):
    return led.LED(self)

  @DUTProperty
  def memory(self):
    return memory.LinuxMemory(self)

  @DUTProperty
  def partitions(self):
    """Returns the partition names of system boot disk."""
    return partitions.Partitions(self)

  @DUTProperty
  def wifi(self):
    return wifi.WiFi(self)

  @DUTProperty
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

  @DUTProperty
  def _RemotePath(self):
    """Returns a module to handle path operations on remote DUT.

    self.path will return this object if DUT is not local. Override this to
    change the implementation of remote DUT.
    """
    return path_module.Path(self)

  @DUTProperty
  def power(self):
    return power.Power(self)

  @DUTProperty
  def status(self):
    """Returns live system status (dynamic data like CPU loading)."""
    return status.SystemStatus(self)

  @DUTProperty
  def storage(self):
    return storage.Storage(self)

  @DUTProperty
  def temp(self):
    return temp.TemporaryFiles(self)

  @DUTProperty
  def thermal(self):
    return thermal.ECToolThermal(self)

  @DUTProperty
  def toybox(self):
    return toybox.Toybox(self)

  @DUTProperty
  def udev(self):
    return udev.LocalUdevMonitor(self)

  @DUTProperty
  def usb_c(self):
    return usb_c.USBTypeC(self)

  @DUTProperty
  def vpd(self):
    return vpd.VitalProductData(self)
