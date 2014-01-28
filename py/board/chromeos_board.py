#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Board interface for ChromeOS board."""


import ctypes
import factory_common  # pylint: disable=W0611
import logging
import re

from cros.factory.system.board import Board, BoardException
from cros.factory.utils.process_utils import Spawn


class ChromeOSBoard(Board):
  """Default implementation of the :py:class:`cros.factory.system.board.Board`
  interface.

  Uses standard CrOS tools (such as ``ectool``) to perform operations.

  This should not be instantiated directly; instead use
  :py:func:`cros.factory.system.GetBoard`.
  """
  # pylint: disable=W0223
  GET_FAN_SPEED_RE = re.compile('Current fan RPM: ([0-9]*)')
  TEMPERATURE_RE = re.compile('^(\d+): (\d+)$', re.MULTILINE)
  TEMPERATURE_INFO_RE = re.compile('^(\d+): \d+ (.+)$', re.MULTILINE)
  EC_VERSION_RE = re.compile('^fw_version\s+\|\s+(.+)$', re.MULTILINE)
  I2C_READ_RE = re.compile('I2C port \d+ at \S+ offset \S+ = (0x[0-9a-f]+)')

  # Expected battery info.
  BATTERY_DESIGN_CAPACITY_RE = re.compile('Design capacity:\s+([1-9]\d*)\s+mAh')

  _Spawn = staticmethod(Spawn)

  # Cached main temperature index. Set at the first call to GetTemperature.
  _main_temperature_index = None

  def __init__(self):
    super(ChromeOSBoard, self).__init__()

  def _CallECTool(self, cmd, check=True):
    """Invokes ectool.

    Args:
      cmd: ectool argument list
      check: True to check returncode and raise BoardException for non-zero
          returncode.

    Returns:
      ectool command's stdout.
    """
    p = Spawn(['ectool'] + cmd, read_stdout=True, ignore_stderr=True)
    if check:
      if p.returncode == 252:
        raise BoardException('EC is locked by write protection')
      elif p.returncode != 0:
        raise BoardException('EC returned error %d' % p.returncode)
    return p.stdout_data

  def I2CRead(self, port, addr, reg):
    try:
      ectool_output = self._CallECTool(['i2cread', '16', str(port), str(addr),
                                        str(reg)])
      return int(self.I2C_READ_RE.findall(ectool_output)[0], 16)
    except Exception as e: # pylint: disable=W0703
      raise BoardException('Unable to read from I2C: %s' % e)

  def I2CWrite(self, port, addr, reg, value):
    try:
      self._CallECTool(['i2cwrite', '16', str(port), str(addr),
                       str(reg), str(value)])
    except Exception as e: # pylint: disable=W0703
      raise BoardException('Unable to write to I2C: %s' % e)

  def GetTemperatures(self):
    try:
      ectool_output = self._CallECTool(['temps', 'all'], check=False)
      temps = []
      for match in self.TEMPERATURE_RE.finditer(ectool_output):
        sensor = int(match.group(1))
        while len(temps) < sensor + 1:
          temps.append(None)
        # Convert Kelvin to Celsius and add
        temps[sensor] = int(match.group(2)) - 273 if match.group(2) else None
      return temps
    except Exception as e: # pylint: disable=W0703
      raise BoardException('Unable to get temperatures: %s' % e)

  def GetMainTemperatureIndex(self):
    if self._main_temperature_index is None:
      try:
        names = self.GetTemperatureSensorNames()
        try:
          return names.index('PECI')
        except ValueError:
          raise BoardException('The expected index of PECI cannot be found')
      except Exception as e: # pylint: disable=W0703
        raise BoardException('Unable to get main temperature index: %s' % e)
    return self._main_temperature_index

  def GetTemperatureSensorNames(self):
    try:
      names = []
      ectool_output = self._CallECTool(['tempsinfo', 'all'], check=False)
      for match in self.TEMPERATURE_INFO_RE.finditer(ectool_output):
        sensor = int(match.group(1))
        while len(names) < sensor + 1:
          names.append(None)
        names[sensor] = match.group(2)
      return names
    except Exception as e: # pylint: disable=W0703
      raise BoardException('Unable to get temperature sensor names: %s' % e)

  def GetFanRPM(self):
    try:
      ectool_output = self._CallECTool(['pwmgetfanrpm'], check=False)
      return int(self.GET_FAN_SPEED_RE.findall(ectool_output)[0])
    except Exception as e: # pylint: disable=W0703
      raise BoardException('Unable to get fan speed: %s' % e)

  def SetFanRPM(self, rpm):
    try:
      self._Spawn(
          ['ectool'] +
          (['autofanctrl', 'on'] if rpm == self.AUTO else
           ['pwmsetfanrpm', '%d' % rpm]),
          check_call=True,
          ignore_stdout=True,
          log_stderr_on_error=True)
    except Exception as e: # pylint: disable=W0703
      if rpm == self.AUTO:
        raise BoardException('Unable to set auto fan control: %s' % e)
      else:
        raise BoardException('Unable to set fan speed to %d RPM: %s' % (rpm, e))

  def GetECVersion(self):
    response = self._Spawn(['mosys', 'ec', 'info', '-l'],
                           read_stdout=True,
                           ignore_stderr=True).stdout_data
    return self.EC_VERSION_RE.search(response).group(1)

  def GetMainFWVersion(self):
    return Spawn(['crossystem', 'ro_fwid'],
                 check_output=True).stdout_data.strip()

  def GetECConsoleLog(self):
    return self._CallECTool(['console'], check=False)

  def GetECPanicInfo(self):
    return self._CallECTool(['panicinfo'], check=False)

  def SetChargeState(self, state):
    try:
      if state == Board.ChargeState.CHARGE:
        self._CallECTool(['chargecontrol', 'normal'])
      elif state == Board.ChargeState.IDLE:
        self._CallECTool(['chargecontrol', 'idle'])
      elif state == Board.ChargeState.DISCHARGE:
        self._CallECTool(['chargecontrol', 'discharge'])
      else:
        raise BoardException('Unknown EC charge state: %s' % state)
    except Exception as e:
      raise BoardException('Unable to set charge state: %s' % e)

  def GetChargerCurrent(self):
    return ctypes.c_int16(self.I2CRead(0, 0x12, 0x14)).value

  def GetBatteryCurrent(self):
    return ctypes.c_int16(self.I2CRead(0, 0x16, 0x0a)).value

  def ProbeEC(self):
    try:
      if self._CallECTool(['hello']).find('EC says hello') == -1:
        raise BoardException('Did not find "EC says hello".')
    except Exception as e:
      raise BoardException('Unable to say hello: %s' % e)

  def GetBatteryDesignCapacity(self):
    try:
      m = self.BATTERY_DESIGN_CAPACITY_RE.search(self._CallECTool(['battery']))
      if not m:
        raise BoardException('Design capacity not found.')
      return int(m.group(1))
    except Exception as e:
      raise BoardException('Unable to get battery design capacity: %s' % e)

  def GetBatteryRegisters(self):
    raise NotImplementedError

  def SetLEDColor(self, color, led_name='battery', brightness=None):
    if color not in Board.LEDColor:
      raise ValueError('Invalid color')
    if brightness is not None and not isinstance(brightness, int):
      raise TypeError('Invalid brightness')
    if brightness is not None and not (0 <= brightness <= 100):
      raise ValueError('brightness out-of-range [0, 100]')
    try:
      if color in [Board.LEDColor.AUTO, Board.LEDColor.OFF]:
        color_brightness = color.lower()
      elif brightness is not None:
        scaled_brightness = int(round(brightness / 100.0 * 255))
        color_brightness = '%s=%d' % (color.lower(), scaled_brightness)
      else:
        color_brightness = color.lower()
      self._CallECTool(['led', led_name, color_brightness])
    except Exception as e:
      logging.exception('Unable to set LED color: %s', e)
