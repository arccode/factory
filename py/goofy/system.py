#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import netifaces
import re
import subprocess

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.utils.process_utils import Spawn

# pylint: disable=W0702
# Disable checking of exception types, since we catch all exceptions
# in many places.


class SystemInfo(object):
  '''Static information about the system.

  This is mostly static information that changes rarely if ever
  (e.g., version numbers, serial numbers, etc.).
  '''
  # If not None, an update that is available from the update server.
  update_md5sum = None

  def __init__(self):
    self.serial_number = None
    try:
      self.serial_number = shopfloor.get_serial_number()
    except:
      pass

    self.factory_image_version = None
    try:
      lsb_release = open('/etc/lsb-release').read()
      match = re.search('^GOOGLE_RELEASE=(.+)$', lsb_release,
                re.MULTILINE)
      if match:
        self.factory_image_version = match.group(1)
    except:
      pass

    try:
      self.wlan0_mac = open('/sys/class/net/wlan0/address').read().strip()
    except:
      self.wlan0_mac = None

    try:
      uname = subprocess.Popen(['uname', '-r'], stdout=subprocess.PIPE)
      stdout, _ = uname.communicate()
      self.kernel_version = stdout.strip()
    except:
      self.kernel_version = None

    try:
      self.architecture = Spawn(['uname', '-m'],
                                check_output=True).stdout_data.strip()
    except:
      self.architecture = None

    self.ec_version = None
    try:
      ectool = subprocess.Popen(['mosys', 'ec', 'info', '-l'],
                    stdout=subprocess.PIPE)
      stdout, _ = ectool.communicate()
      match = re.search('^fw_version\s+\|\s+(.+)$', stdout,
                re.MULTILINE)
      if match:
        self.ec_version = match.group(1)
    except:
      pass

    self.firmware_version = None
    try:
      crossystem = subprocess.Popen(['crossystem', 'fwid'],
                      stdout=subprocess.PIPE)
      stdout, _ = crossystem.communicate()
      self.firmware_version = stdout.strip() or None
    except:
      pass

    self.root_device = None
    try:
      rootdev = Spawn(['rootdev', '-s'],
                      stdout=subprocess.PIPE)
      stdout, _ = rootdev.communicate()
      self.root_device = stdout.strip()
    except:
      pass

    self.factory_md5sum = factory.get_current_md5sum()

    # update_md5sum is currently in SystemInfo's __dict__ but not this
    # object's.  Copy it from SystemInfo into this object's __dict__.
    self.update_md5sum = SystemInfo.update_md5sum


def GetIPv4Addresses():
  '''Returns a string describing interfaces' IPv4 addresses.

  The returned string is of the format

    eth0=192.168.1.10, wlan0=192.168.16.14
  '''
  ret = []
  for i in sorted(netifaces.interfaces()):
    if i.startswith('lo'):
      # Boring
      continue

    try:
      addresses = netifaces.ifaddresses(i).get(netifaces.AF_INET, [])
    except ValueError:
      continue

    ips = [x.get('addr') for x in addresses
           if 'addr' in x] or ['none']

    ret.append('%s=%s' % (i, '+'.join(ips)))

  return ', '.join(ret)


class SystemStatus(object):
  '''Information about the current system status.

  This is information that changes frequently, e.g., load average
  or battery information.

  We log a bunch of system status here.
  '''

  GET_FAN_SPEED_RE = re.compile('Current fan RPM: ([0-9]*)')
  TEMP_SENSOR_RE = re.compile('Reading temperature...([0-9]*)')
  TEMPERATURE_RE = re.compile('^(\d+): (\d+)$', re.MULTILINE)
  TEMPERATURE_INFO_RE = re.compile('^(\d+): \d+ (.+)$', re.MULTILINE)

  def __init__(self):
    self.battery = {}
    for k, item_type in [('charge_full', int),
                         ('charge_full_design', int),
                         ('charge_now', int),
                         ('current_now', int),
                         ('present', bool),
                         ('status', str),
                         ('voltage_min_design', int),
                         ('voltage_now', int)]:
      try:
        self.battery[k] = item_type(
          open('/sys/class/power_supply/BAT0/%s' % k).read().strip())
      except:
        self.battery[k] = None

    # Get fan speed
    self.fan_rpm = self.GetFanSpeed()

    # Get temperatures from sensors
    try:
      self.temperatures = self._ParseTemperatures(
          self.CallECTool(['temps', 'all']))
    except:
      self.temperatures = []

    try:
      self.main_temperature_index = self._ParseTemperatureInfo(
          self.CallECTool(['tempsinfo', 'all'])).index('PECI')
    except:
      self.main_temperature_index = None

    try:
      self.load_avg = map(
        float, open('/proc/loadavg').read().split()[0:3])
    except:
      self.load_avg = None

    try:
      self.cpu = map(int, open('/proc/stat').readline().split()[1:])
    except:
      self.cpu = None

    try:
      self.ips = GetIPv4Addresses()
    except:
      self.ips = None

  @staticmethod
  def _ParseTemperatures(ectool_output):
    '''Returns a list of temperatures for various sensors.

    Args:
      ectool_output: Output of "ectool temps all".
    '''
    temps = []
    for match in SystemStatus.TEMPERATURE_RE.finditer(ectool_output):
      sensor = int(match.group(1) or match.group(3))
      while len(temps) < sensor + 1:
        temps.append(None)
      # Convert Kelvin to Celsius and add
      temps[sensor] = int(match.group(2)) - 273 if match.group(2) else None
    return temps

  @staticmethod
  def _ParseTemperatureInfo(ectool_output):
    '''Returns a list of temperatures for various sensors.

    Args:
      ectool_output: Output of "ectool tempsinfo all".
    '''
    infos = []
    for match in SystemStatus.TEMPERATURE_INFO_RE.finditer(ectool_output):
      sensor = int(match.group(1))
      while len(infos) < sensor + 1:
        infos.append(None)
      infos[sensor] = match.group(2)
    return infos

  def CallECTool(self, cmd):
    full_cmd = ['ectool'] + cmd
    return Spawn(full_cmd, read_stdout=True, ignore_stderr=True).stdout_data

  def GetFanSpeed(self):
    try:
      response = self.CallECTool(['pwmgetfanrpm'])
      return int(self.GET_FAN_SPEED_RE.findall(response)[0])
    except Exception: # pylint: disable=W0703
      return None

  def GetTemperature(self, idx):
    try:
      response = self.CallECTool(['temps', '%d' % idx])
      return int(self.TEMP_SENSOR_RE.findall(response)[0])
    except Exception: # pylint: disable=W0703
      return None

if __name__ == '__main__':
  import yaml
  print yaml.dump(dict(system_info=SystemInfo(None, None).__dict__,
             system_status=SystemStatus().__dict__),
          default_flow_style=False)

