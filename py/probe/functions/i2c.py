# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import subprocess

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.utils.arg_utils import Arg


EC_BUS_PREFIX = 'EC-'
ADDR_START = 0x03
ADDR_END = 0x77


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


class I2CFunction(function.ProbeFunction):
  """Probes the I2C device."""

  ARGS = [
      Arg('bus', str,
          'The I2C bus number. Every bus will be scanned if it is not '
          'assigned. If the bus is behind EC, then it should have "%s" prefix. '
          'For example: "%s0"' % (EC_BUS_PREFIX, EC_BUS_PREFIX),
          optional=True),
      Arg('addr', str,
          'The address of the device. Every address between %s and %s will be '
          'scanned if it is not assigned.' %
          (Hexify(ADDR_START), Hexify(ADDR_END)),
          optional=True),
      Arg('use_r_flag', bool, 'Use SMBus "read byte" commands for probing.',
          default=False),
  ]

  def Probe(self):
    ret = []
    bus_list = self.GetBusList() if self.args.bus is None else [self.args.bus]
    addr_list = (self.GetAddrList() if self.args.addr is None
                 else [self.args.addr])
    for bus in bus_list:
      for addr in addr_list:
        logging.debug('Probe I2C %s:%s', bus, addr)
        addr = Hexify(addr)
        try:
          if bus.startswith(EC_BUS_PREFIX):
            exists = self.ProbeECI2C(bus[len(EC_BUS_PREFIX):], addr)
          else:
            exists = self.ProbeI2C(bus, addr)
        except Exception:
          continue
        if exists:
          ret.append({
              'bus': bus,
              'addr': addr})
    return ret

  def GetBusList(self):
    """Returns a list that contains all buses."""
    cmd = 'i2cdetect -l | wc -l'
    count = subprocess.check_output(cmd, shell=True)
    ap_bus = map(str, range(int(count)))
    # TODO(akahuang): Find a way to get all EC I2C busses.
    ec_bus = range(5)
    return ap_bus + [EC_BUS_PREFIX + str(bus) for bus in ec_bus]

  def GetAddrList(self):
    """Returns a list that contains all address."""
    return range(ADDR_START, ADDR_END + 1)

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
      output = subprocess.check_output(cmd)
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

