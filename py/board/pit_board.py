#!/usr/bin/python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
import logging

from cros.factory.board.chromeos_board import ChromeOSBoard

class PitBoard(ChromeOSBoard):
  """Board interface for Pit."""

  def GetTemperatures(self):
    with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
      return [int(f.readline().rstrip())/1000]

  def GetMainTemperatureIndex(self):
    return 0

  def GetTemperatureSensorNames(self):
    return ['CPU']

  def SetChargeState(self, state):
    #TODO: Add an actual SetChargeState implementation
    logging.info('SetChargeState: Non-functional. See crosbug.com/p/19417')

  def GetChargerCurrent(self):
    raise NotImplementedError
