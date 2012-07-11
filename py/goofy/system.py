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
      rootdev = subprocess.Popen(['rootdev', '-s'],
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
  '''
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

if __name__ == '__main__':
  import yaml
  print yaml.dump(dict(system_info=SystemInfo(None, None).__dict__,
             system_status=SystemStatus().__dict__),
          default_flow_style=False)

