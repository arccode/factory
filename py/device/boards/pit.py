# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

from cros.factory.device.boards import chromeos
from cros.factory.device import device_types
from cros.factory.device import power


class PitPower(power.Power):

  def SetChargeState(self, state):
    # TODO: Add an actual SetChargeState implementation
    logging.info('SetChargeState: Non-functional. See crosbug.com/p/19417')

  def GetChargerCurrent(self):
    raise NotImplementedError


class PitBoard(chromeos.ChromeOSBoard):
  """Board interface for Pit."""

  @device_types.DeviceProperty
  def power(self):
    return PitPower(self)
