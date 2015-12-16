#!/usr/bin/python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component
from cros.factory.test.dut import power
from cros.factory.test.dut import thermal
from cros.factory.test.dut.boards import chromeos


class PitThermal(thermal.Thermal):

  def GetTemperatures(self):
    raw = self._dut.ReadFile('/sys/class/thermal/thermal_zone0/temp')
    return [int(raw.splitlines()[0].rstrip()) / 1000]

  def GetMainTemperatureIndex(self):
    return 0

  def GetTemperatureSensorNames(self):
    return ['CPU']


class PitPower(power.Power):

  def SetChargeState(self, state):
    # TODO: Add an actual SetChargeState implementation
    logging.info('SetChargeState: Non-functional. See crosbug.com/p/19417')

  def GetChargerCurrent(self):
    raise NotImplementedError


class PitBoard(chromeos.ChromeOSBoard):
  """Board interface for Pit."""

  @component.DUTProperty
  def power(self):
    return PitPower(self)

  @component.DUTProperty
  def thermal(self):
    return PitThermal(self)
