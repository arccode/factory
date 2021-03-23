# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""ChromeOS family boards."""

from cros.factory.device.boards import linux
from cros.factory.device import device_types
from cros.factory.utils import type_utils


class ChromeOSBoard(linux.LinuxBoard):
  """Common interface for ChromeOS boards."""

  @device_types.DeviceProperty
  def audio(self):
    from cros.factory.device.audio import utils as audio_utils
    return audio_utils.CreateAudioControl(
        self, controller=audio_utils.CONTROLLERS.ALSA)

  @device_types.DeviceProperty
  def bluetooth(self):
    from cros.factory.device.chromeos import bluetooth
    return bluetooth.ChromeOSBluetoothManager(self)

  @device_types.DeviceProperty
  def camera(self):
    from cros.factory.device.chromeos import camera
    return camera.ChromeOSCamera(self)

  @device_types.DeviceProperty
  def display(self):
    from cros.factory.device.chromeos import display
    return display.ChromeOSDisplay(self)

  @device_types.DeviceProperty
  def fan(self):
    from cros.factory.device import fan
    return fan.ECToolFanControl(self)

  @device_types.DeviceProperty
  def power(self):
    from cros.factory.device import power
    return power.ChromeOSPower(self)

  @device_types.DeviceProperty
  def wifi(self):
    from cros.factory.device import wifi
    return wifi.WiFiChromeOS(self)

  @device_types.DeviceProperty
  def vpd(self):
    from cros.factory.device import vpd
    return vpd.ChromeOSVitalProductData(self)

  @type_utils.Overrides
  def GetStartupMessages(self):
    res = super(ChromeOSBoard, self).GetStartupMessages()

    mosys_log = self.CallOutput(
        ['mosys', 'eventlog', 'list'], stderr=self.STDOUT)

    if mosys_log:
      res['mosys_log'] = mosys_log

    return res
