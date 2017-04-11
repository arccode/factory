#!/usr/bin/python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

import factory_common  # pylint: disable=W0611
from cros.factory.device import component
from cros.factory.device import power
from cros.factory.device.boards import chromeos


class PitPower(power.Power):

  def SetChargeState(self, state):
    # TODO: Add an actual SetChargeState implementation
    logging.info('SetChargeState: Non-functional. See crosbug.com/p/19417')

  def GetChargerCurrent(self):
    raise NotImplementedError


class PitBoard(chromeos.ChromeOSBoard):
  """Board interface for Pit."""

  @component.DeviceProperty
  def power(self):
    return PitPower(self)
