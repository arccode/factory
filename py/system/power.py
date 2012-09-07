#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import os

from cros.factory.test.utils import Enum, ReadOneLine

class PowerException(Exception):
  pass


class Power(object):
  # Power source types
  PowerSource = Enum(['BATTERY', 'MAINS'])

  _sys = '/sys'

  def __init__(self):
    self._battery_path = None
    self._current_state = None

  def FindPowerPath(self, power_source):
    '''Find battery path in sysfs.'''
    if power_source == self.PowerSource.BATTERY:
      power_type = 'Battery'
    else:
      power_type = 'Mains'
    for p in glob.glob(os.path.join(self._sys, "class/power_supply/*/type")):
      if ReadOneLine(p) == power_type:
        return os.path.dirname(p)
    raise PowerException("Cannot find %s" % power_type)

  def CheckACPresent(self):
    '''Check if AC power is present.'''
    try:
      p = self.FindPowerPath(self.PowerSource.MAINS)
      return ReadOneLine(os.path.join(p, "online")) == "1"
    except (PowerException, IOError):
      return False

  def CheckBatteryPresent(self):
    '''Check if battery is present and also set battery path.'''
    try:
      self._battery_path = self.FindPowerPath(self.PowerSource.BATTERY)
      return True
    except PowerException:
      return False

  def GetChargePct(self):
    '''Get current charge level in percentage.'''
    try:
      charge_now = ReadOneLine(self._battery_path + '/charge_now')
      charge_full = ReadOneLine(self._battery_path + '/charge_full')
    except IOError:
      # Battery driver is not fully initialized
      return None

    if float(charge_full) <= 0:
      return None # Something wrong with the battery
    return round(float(charge_now) * 100.0 / float(charge_full))
