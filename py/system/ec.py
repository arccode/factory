#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=R0922

import factory_common # pylint: disable=W0611

from cros.factory.test.utils import Enum


class ECException(Exception):
  pass


class EC(object):
  '''Basic EC interface class.'''
  ChargeState = Enum(['CHARGE', 'IDLE', 'DISCHARGE'])

  # Auto fan speed.
  AUTO = 'auto'

  # Functions that are used in Goofy. Must be implemented.
  def GetTemperatures(self):
    '''Gets a list of temperatures for various sensors.

    Returns:
      A list of int indicating the temperatures in Celsius. Raises ECException
      when fail.'''
    raise NotImplementedError

  def GetMainTemperatureIndex(self):
    '''Gets the main index in temperatures list that should be logged.

    This is typically the CPU temperature.

    Returns:
      A int indicating the main temperature index. Raises ECException when
      fail.'''
    raise NotImplementedError

  def GetFanRPM(self):
    '''Gets the fan RPM.

    Returns:
      A int indicating the fan RPM. Raises ECException when fail.'''
    raise NotImplementedError

  def GetVersion(self):
    '''Gets the EC firmware version.

    Returns:
      A string of the EC firmware version. Raises ECException when fail.'''
    raise NotImplementedError

  def GetConsoleLog(self):
    '''Gets the EC console log.

    Returns:
      A string containing EC console log. Raises ECException when fail.'''
    raise NotImplementedError

  def SetChargeState(self, state):
    '''Sets the charge state.

    Args:
      state: One of the three states in ChargeState.

    Returns:
      Raises ECException when fail.
    '''
    raise NotImplementedError

  # Optional functions. Implement them if you need them in your tests.
  def SetFanRPM(self, rpm):
    '''Sets the target fan RPM.

    Args:
      rpm: Target fan RPM, or AUTO for auto.

    Returns:
      Raises ECException when fail.
    '''
    raise NotImplementedError
