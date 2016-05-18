#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""ChromeOS family boards."""

import factory_common  # pylint: disable=W0611
from cros.factory.device.audio import utils as audio_utils
from cros.factory.device import component
from cros.factory.device import wifi
from cros.factory.device.boards import linux
from cros.factory.device.chromeos import bluetooth
from cros.factory.device.chromeos import display
from cros.factory.device import vpd


class ChromeOSBoard(linux.LinuxBoard):
  """Common interface for ChromeOS boards."""

  @component.DeviceProperty
  def audio(self):
    return audio_utils.CreateAudioControl(
        self, controller=audio_utils.CONTROLLERS.ALSA)

  @component.DeviceProperty
  def bluetooth(self):
    return bluetooth.ChromeOSBluetoothManager(self)

  @component.DeviceProperty
  def display(self):
    return display.ChromeOSDisplay(self)

  @component.DeviceProperty
  def wifi(self):
    return wifi.WiFiChromeOS(self)

  @component.DeviceProperty
  def vpd(self):
    return vpd.ChromeOSVitalProductData(self)
