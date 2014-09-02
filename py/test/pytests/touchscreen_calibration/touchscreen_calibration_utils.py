# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common utility functions that are not touch specific.

The SimpleSystem() and SimpleSystemOutput() functions are grabbed from
hardware_Trackpad and were written by truty@.

Note that in order to be able to use this module on a system without the
factory stuffs, e.g., on a Beagle Bone, this module does not depend on
any factory modules on purpose.
"""

from __future__ import print_function

import glob
import logging
import os
import re
import subprocess

from subprocess import PIPE, STDOUT


_SYSFS_I2C_PATH = '/sys/bus/i2c/devices'
_DEBUG_PATH = '/sys/kernel/debug'

ATMEL = 'atmel'
_TOUCH_DRIVER = {ATMEL: 'atmel_mxt_ts'}
_TOUCH_CONFIG = {ATMEL: 'maxtouch-ts.cfg'}


class Error(Exception):
  pass


def SimpleSystem(cmd):
  """Execute a system command."""
  ret = subprocess.call(cmd, shell=True)
  if ret:
    logging.warning('Command (%s) failed (ret=%s).', cmd, ret)
  return ret


def SimpleSystemOutput(cmd):
  """Execute a system command and get its output."""
  try:
    proc = subprocess.Popen(cmd, shell=True, stdout=PIPE, stderr=STDOUT)
    stdout, _ = proc.communicate()
  except Exception, e:
    logging.warning('Command (%s) failed (%s).', cmd, e)
  else:
    return None if proc.returncode else stdout.strip()


def IsDestinationPortEnabled(port):
  """Check if the destination port is enabled.

  If port 8000 is enabled, it looks like
    ACCEPT  tcp  --  0.0.0.0/0  0.0.0.0/0  ctstate NEW tcp dpt:8000
  """
  pattern = re.compile('ACCEPT\s+tcp\s+0.0.0.0/0\s+0.0.0.0/0\s+ctstate\s+'
                       'NEW\s+tcp\s+dpt:%d' % port)
  rules = SimpleSystemOutput('iptables -L INPUT -n --line-number')
  for rule in rules.splitlines():
    if pattern.search(rule):
      return True
  return False


def EnableDestinationPort(port):
  """Eanble the destination port in iptables."""
  cmd = ('iptables -A INPUT -p tcp -m conntrack --ctstate NEW --dport %d '
         '-j ACCEPT' % port)
  if SimpleSystem(cmd) != 0:
    raise Error('Failed to enable destination port in iptables: %d.' % port)


def GetSysfsEntry(vendor=ATMEL):
  """Get the sys fs object file which is used to tune the device registers.

  Args:
    device_names: a list of possible device names

  A qualifying device should satisfy the following 2 conditions.
  Cond 1: Get those device paths with the matching driver name for the vendor.
          The device path looks like: '/sys/bus/i2c/devices/...'.
          An example about Samus
          For touchpad device:
          i2c-ATML0000:01/driver -> ../../../../../bus/i2c/drivers/atmel_mxt_ts
          For touchscreen device:
          i2c-ATML0001:01/driver -> ../../../../../bus/i2c/drivers/atmel_mxt_ts
          Note that both touch devices use the same driver.

  Cond 2: If there are multiple device paths with the same driver, use the
          config name to distinguish them. Here we assume that different
          touch devices would use different configs. As an example, on Samus
          the config name of its touchpad is maxtouch-tp.cfg, while
          the config name of its touchscreen is maxtouch-ts.cfg.

  Returns: the sys fs path of the target touch device
           e.g., '/sys/bus/i2c/devices/i2c-ATML0001:01'
  """
  def MatchingDriver(path, vendor):
    """Cond 1: Matching the path with the vendor associated driver."""
    expected_driver = _TOUCH_DRIVER.get(vendor)
    actual_driver = os.path.basename(
        os.path.realpath(os.path.join(path, 'driver')))
    return actual_driver == expected_driver

  def MatchingConfig(path, vendor):
    """Cond 2: Matching the path with the vendor associated config."""
    config_file = os.path.join(path, 'config_file')
    if not os.path.isfile(config_file):
      return False
    with open(config_file) as f:
      return f.read().strip() == _TOUCH_CONFIG.get(vendor)

  device_paths = []
  for path in glob.glob(os.path.join(_SYSFS_I2C_PATH, '*')):
    if MatchingDriver(path, vendor) and MatchingConfig(path, vendor):
      device_paths.append(path)

  # If there are multiple qualifying sysfs paths which is very unlikely,
  # just use the first one.
  return os.path.join(device_paths[0], 'object') if device_paths else None


def GetDebugfs(vendor=ATMEL):
  """Get the kernel debug path for the specified device.

  Args:
    vendor: a vendor name, e.g., 'atmel'

  Returns: the kernel debug fs path of the touch device
           e.g., driver is 'atmel_mxt_ts' and i2c_device is 'i2c-ATML0001:01',
                 return '/sys/kernel/debug/atmel_mxt_ts/i2c-ATML0001:01'
  """
  driver = _TOUCH_DRIVER.get(vendor)
  sysfs_entry = GetSysfsEntry()
  if driver is None or sysfs_entry is None:
    return None
  i2c_device = os.path.basename(os.path.dirname(sysfs_entry))
  device_debug_path = os.path.join(_DEBUG_PATH, driver, i2c_device)
  object_file = os.path.join(device_debug_path, 'object')
  return device_debug_path if os.path.isfile(object_file) else None
