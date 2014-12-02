# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Board interface for ChromeOS board."""

from __future__ import print_function

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
  GET_FAN_SPEED_RE = re.compile(r'Fan (\d+) RPM: (\d+)')
  TEMPERATURE_RE = re.compile(r'^(\d+): (\d+)$', re.MULTILINE)
  TEMPERATURE_INFO_RE = re.compile(r'^(\d+): \d+ (.+)$', re.MULTILINE)
  I2C_READ_RE = re.compile(r'I2C port \d+ at \S+ offset \S+ = (0x[0-9a-f]+)')
  EC_BATTERY_RE = re.compile(r'^\s+Present current\s+(\d+)\s+mA$', re.MULTILINE)
  EC_BATTERY_CHARGING_RE = re.compile(r'^\s+Flags\s+.*\s+CHARGING.*$',
      re.MULTILINE)
  EC_CHARGER_RE = re.compile(r'^chg_current = (\d+)mA$', re.MULTILINE)

  # Expected battery info.
  BATTERY_DESIGN_CAPACITY_RE = re.compile('Design capacity:\s+([1-9]\d*)\s+mAh')

  # USB PD info.
  USB_PD_INFO_RE = re.compile(
      r'Port C(?P<port>\d+) is (?P<enabled>enabled|disabled), '
      r'Role:(?P<role>SRC|SNK) Polarity:(?P<polarity>CC1|CC2) '
      r'State:(?P<state>\d+)')

  # EC tool arguments for accessing PD. Subclass may override this to match the
  # arguments used on the actual board.
  ECTOOL_PD_ARGS = ['--interface=lpc', '--dev=1']

  _Spawn = staticmethod(Spawn)

  # Cached main temperature index. Set at the first call to GetTemperature.
  _main_temperature_index = None

  # Cached temperature sensor names.
  _temperature_sensor_names = None

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
    except Exception as e:  # pylint: disable=W0703
      raise BoardException('Unable to read from I2C: %s' % e)

  def I2CWrite(self, port, addr, reg, value):
    try:
      self._CallECTool(['i2cwrite', '16', str(port), str(addr),
                        str(reg), str(value)])
    except Exception as e:  # pylint: disable=W0703
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
    except Exception as e:  # pylint: disable=W0703
      raise BoardException('Unable to get temperatures: %s' % e)

  def GetMainTemperatureIndex(self):
    if self._main_temperature_index is not None:
      return self._main_temperature_index
    try:
      names = self.GetTemperatureSensorNames()
      try:
        self._main_temperature_index = names.index('PECI')
        return self._main_temperature_index
      except ValueError:
        raise BoardException('The expected index of PECI cannot be found')
    except Exception as e:  # pylint: disable=W0703
      raise BoardException('Unable to get main temperature index: %s' % e)

  def GetTemperatureSensorNames(self):
    if self._temperature_sensor_names is not None:
      return list(self._temperature_sensor_names)
    try:
      names = []
      ectool_output = self._CallECTool(['tempsinfo', 'all'], check=False)
      for match in self.TEMPERATURE_INFO_RE.finditer(ectool_output):
        sensor = int(match.group(1))
        while len(names) < sensor + 1:
          names.append(None)
        names[sensor] = match.group(2)
      self._temperature_sensor_names = names
      return list(names)
    except Exception as e:  # pylint: disable=W0703
      raise BoardException('Unable to get temperature sensor names: %s' % e)

  def GetFanRPM(self, fan_id=None):
    try:
      ectool_output = self._CallECTool(
          ['pwmgetfanrpm'] + (['%d' % fan_id] if fan_id is not None else []),
          check=False)
      return [int(rpm[1])
              for rpm in self.GET_FAN_SPEED_RE.findall(ectool_output)]
    except Exception as e:  # pylint: disable=W0703
      raise BoardException('Unable to get fan speed: %s' % e)

  def SetFanRPM(self, rpm, fan_id=None):
    try:
      # For system with multiple fans, ectool controls all the fans
      # simultaneously in one command.
      if rpm == self.AUTO:
        self._Spawn((['ectool', 'autofanctrl'] +
                     (['%d' % fan_id] if fan_id is not None else [])),
                    check_call=True, ignore_stdout=True,
                    log_stderr_on_error=True)
      else:
        self._Spawn((['ectool', 'pwmsetfanrpm'] +
                     (['%d' % fan_id] if fan_id is not None else []) +
                     ['%d' % rpm]),
                    check_call=True, ignore_stdout=True,
                    log_stderr_on_error=True)
    except Exception as e:  # pylint: disable=W0703
      if rpm == self.AUTO:
        raise BoardException('Unable to set auto fan control: %s' % e)
      else:
        raise BoardException('Unable to set fan speed to %d RPM: %s' % (rpm, e))

  def GetECVersion(self):
    return self._Spawn(['mosys', 'ec', 'info', '-s', 'fw_version'],
                       read_stdout=True, ignore_stderr=True).stdout_data.strip()

  def GetPDVersion(self):
    return self._Spawn(['mosys', 'pd', 'info', '-s', 'fw_version'],
                       read_stdout=True, ignore_stderr=True).stdout_data.strip()

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
    ectool_output = None
    try:
      ectool_output = self._CallECTool(['chargestate', 'show'])
    except BoardException:
      return ctypes.c_int16(self.I2CRead(0, 0x12, 0x14)).value

    re_object = self.EC_CHARGER_RE.findall(ectool_output)
    if re_object:
      return int(re_object[0])
    else:
      raise BoardException('Cannot find current in ectool chargestate show')

  def GetBatteryCurrent(self):
    ectool_output = None
    try:
      ectool_output = self._CallECTool(['battery'])
    except BoardException:
      return ctypes.c_int16(self.I2CRead(0, 0x16, 0x0a)).value

    charging = bool(self.EC_BATTERY_CHARGING_RE.search(ectool_output))
    re_object = self.EC_BATTERY_RE.findall(ectool_output)
    if re_object:
      current = int(re_object[0])
    else:
      raise BoardException('Cannot find current in ectool battery output')
    return current if charging else -current

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

  def GetBoardVersion(self):
    try:
      response = self._Spawn(['mosys', 'platform', 'version'],
                             read_stdout=True, check_call=True,
                             ignore_stderr=True).stdout_data
    except Exception as e:
      raise BoardException('Unable to get board version: %s' % e)
    else:
      return response.strip()

  def GetUSBPDStatus(self, port):
    response = self._CallECTool(self.ECTOOL_PD_ARGS + ['usbpd', '%d' % port])
    match = self.USB_PD_INFO_RE.match(response)
    if not match:
      raise BoardException('Unable to parse USB PD status from: %s' % response)
    return dict(
        enabled=match.group('enabled') == 'enabled',
        role=match.group('role'),
        polarity=match.group('polarity'),
        state=int(match.group('state')))

  def CheckACPresent(self):
    return self.power.CheckACPresent()
