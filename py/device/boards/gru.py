# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

from cros.factory.device.boards import chromeos
from cros.factory.device import device_types
from cros.factory.device import power


class GruPower(power.Power):

  def SetChargeState(self, state):
    # TODO: Add an actual SetChargeState implementation
    logging.info('SetChargeState: Non-functional. See crosbug.com/p/19417')

  def GetChargerCurrent(self):
    raise NotImplementedError


class GruBoard(chromeos.ChromeOSBoard):
  """Reference implementation for RK3399 platform."""

  @device_types.DeviceProperty
  def power(self):
    return GruPower(self)
