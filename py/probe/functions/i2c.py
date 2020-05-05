# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import os
import subprocess

from cros.factory.probe.lib import probe_function
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils


SYSFS_I2C_DIR_PATH = '/sys/bus/i2c/devices'
I2C_BUS_PREFIX = 'i2c-'
EC_BUS_PREFIX = 'EC-'
ADDR_START = 0x03
ADDR_END = 0x77


def _GetBusNumber(condition_func):
  """Gets the I2C numbers which satisfy the condition function.

  Args:
    condition_func: a function whose input is a path of sysfs node, and returns
      a boolean value.

  Returns:
    a list of strings indicating the I2C bus numbers.
  """
  ret = []
  for node in glob.glob(os.path.join(SYSFS_I2C_DIR_PATH, I2C_BUS_PREFIX + '*')):
    try:
      if condition_func(node):
        ret.append(os.path.basename(node)[len(I2C_BUS_PREFIX):])
    except Exception:
      pass
  return ret


def GetBusNumberByPath(bus_path):
  """Gets the I2C numbers by the realpath of the sysfs node."""
  def ConditionFunc(node):
    return os.path.realpath(node).startswith(bus_path)
  return _GetBusNumber(ConditionFunc)


def GetBusNumberByName(bus_name):
  """Gets the I2C numbers by the I2C bus name."""
  def ConditionFunc(node):
    with open(os.path.join(node, 'name'), 'r') as f:
      return f.read().strip() == bus_name
  return _GetBusNumber(ConditionFunc)


def GetBusInfo(bus_number):
  """Get the extra information of the I2C bus.

  Args:
    bus_number: the I2C bus number.

  Returns:
    a dict including the I2C bus name and the real path of the sysfs node.
  """
  node_path = os.path.join(SYSFS_I2C_DIR_PATH, I2C_BUS_PREFIX + str(bus_number))
  if bus_number.startswith(EC_BUS_PREFIX) or not os.path.exists(node_path):
    return {}

  with open(os.path.join(node_path, 'name'), 'r') as f:
    bus_name = f.read().strip()
  bus_path = os.path.dirname(os.path.realpath(node_path))
  return {
      'bus_name': bus_name,
      'bus_path': bus_path}


def Hexify(value):
  """Returns the hexified string of the value.

  Args:
    value: integer or string.

  Returns:
    a string whose format looks like "0x0b".
  """
  if isinstance(value, int):
    number = value
  elif value.startswith('0x'):
    number = int(value, 16)
  else:
    number = int(value, 10)
  return '0x%02x' % number


class I2CFunction(probe_function.ProbeFunction):
  """Probes the I2C device.

  Description
  -----------
  This function probes a specific bus/address to check whether an I2C device
  is connected there or not.

  The probed result for a single I2C device is a dictionary which contains
  at least two entries, one is ``bus_number`` and the other one is ``addr``.

  Examples
  --------
  Let's say we've already known that the address of I2C camera X is 0x24 but
  we don't know which bus that camera is connected.  A not 100% reliable way
  to verify whether camera X is installed or not on the device is to write
  the probe statement ::

    {
      "eval": {
        "i2c": {
          "addr": "0x24"
        }
      }
    }

  The function will try to probe ``address 0x24`` on all I2C buses.  If camera
  X is found at bus 2, we will have below probed results::

    [
      {
        "addr": "0x24",
        "bus_number": "2"
      }
    ]

  Otherwise the probed results might be just an empty list.  Howerver, it's
  possible that another I2C device has the address number ``0x24`` on another
  bus too.  In this case, the probe statement above will lead to a false
  positive result.
  """

  ARGS = [
      Arg('bus_number', str,
          'The I2C bus number. Every bus will be scanned if it is not '
          'assigned. If the bus is behind EC, then it should have "%s" prefix. '
          'For example: "%s0"' % (EC_BUS_PREFIX, EC_BUS_PREFIX),
          default=None),
      Arg('bus_path', str,
          'The realpath of the I2C bus sysfs node. Ignored if `bus_number` '
          'argument is given.',
          default=None),
      Arg('bus_name', str,
          'The name of the I2C bus sysfs node. Ignored if `bus_number` '
          'argument is given.',
          default=None),
      Arg('addr', str,
          'The address of the device. Every address between %s and %s will be '
          'scanned if it is not assigned.' %
          (Hexify(ADDR_START), Hexify(ADDR_END)),
          default=None),
      Arg('use_r_flag', bool, 'Use SMBus "read byte" commands for probing.',
          default=False),
  ]

  def Probe(self):
    ret = []
    if self.args.bus_number:
      bus_list = [self.args.bus_number]
    else:
      bus_list = set(self.GetBusList())
      if self.args.bus_path:
        bus_list &= set(GetBusNumberByPath(self.args.bus_path))
      if self.args.bus_name:
        bus_list &= set(GetBusNumberByName(self.args.bus_name))
    addr_list = (self.GetAddrList() if self.args.addr is None
                 else [self.args.addr])
    for bus_number in bus_list:
      for addr in addr_list:
        logging.debug('Probe I2C %s:%s', bus_number, addr)
        addr = Hexify(addr)
        try:
          if bus_number.startswith(EC_BUS_PREFIX):
            exists = self.ProbeECI2C(bus_number[len(EC_BUS_PREFIX):], addr)
          else:
            exists = self.ProbeI2C(bus_number, addr)
        except Exception:
          continue
        if exists:
          result = {
              'bus_number': bus_number,
              'addr': addr}
          result.update(GetBusInfo(bus_number))
          ret.append(result)
    return ret

  def GetBusList(self):
    """Returns a list that contains all buses."""
    cmd = 'i2cdetect -l | wc -l'
    count = subprocess.check_output(cmd, shell=True)
    ap_bus = list(map(str, list(range(int(count)))))
    # TODO(akahuang): Find a way to get all EC I2C busses.
    ec_bus = list(range(5))
    return ap_bus + [EC_BUS_PREFIX + str(bus) for bus in ec_bus]

  def GetAddrList(self):
    """Returns a list that contains all address."""
    return list(range(ADDR_START, ADDR_END + 1))

  def ProbeI2C(self, bus, addr):
    """Probes to see if there is an I2C device in the address of the bus.

    Args:
      bus: a string to indicate the bus number.
      addr: a string to indicate the address in hexadecimal. Format: '0x0b'

    Returns:
      True if the I2C device is detected.
    """
    cmd = ['i2cdetect']
    if self.args.use_r_flag:
      cmd.append('-r')
    cmd += ['-y', bus, addr, addr]
    try:
      output = process_utils.CheckOutput(cmd)
    except subprocess.CalledProcessError:
      return False

    lines = output.splitlines()[1:]  # The first line is title row.
    items = []
    for line in lines:
      items += line.split()[1:]  # The first item in each line is title column.
    return 'UU' in items or addr[2:] in items

  def ProbeECI2C(self, bus, addr):
    """Probe if there is a I2C device in the address of the bus behind EC.

    Args:
      bus: a string to indicate the bus number.
      addr: a string to indicate the address in hexadecimal. Format: '0x0b'
    """
    cmd = ['ectool', 'i2cxfer', bus, addr, '1', '0']
    return subprocess.call(cmd) == 0
