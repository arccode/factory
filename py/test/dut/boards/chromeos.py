#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""ChromeOS family boards."""

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component
from cros.factory.test.dut import wifi
from cros.factory.test.dut.boards import linux
from cros.factory.test.dut.chromeos import bluetooth
from cros.factory.test.dut.chromeos import display
from cros.factory.test.dut import vpd


class ChromeOSBoard(linux.LinuxBoard):
  """Common interface for ChromeOS boards."""

  @component.DUTProperty
  def bluetooth(self):
    return bluetooth.ChromeOSBluetoothManager(self)

  @component.DUTProperty
  def display(self):
    return display.ChromeOSDisplay(self)

  @component.DUTProperty
  def wifi(self):
    return wifi.WiFiChromeOS(self)

  @component.DUTProperty
  def vpd(self):
    return vpd.ChromeOSVitalProductData(self)
