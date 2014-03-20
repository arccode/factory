# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Checks EXT_CSD value in eMMC.

Some eMMC vendors publish device version in proprietary field in ext_csd[].

This test a temporary solution to check device version. It's better if the
vendor can update eMMC 4.x cid.prv field, which is already probed in HWID.

"""

from glob import glob
import logging
import os
import re
import unittest

import factory_common  # pylint: disable=W0611

from cros.factory.test.args import Arg
from cros.factory.test.factory import FactoryTestFailure
from cros.factory.utils.process_utils import CheckOutput, GetLines


class VerifyMMCFirmware(unittest.TestCase):
  ARGS = [
    Arg('ext_csd_index', int, 'Index of EXT_CSD to check.'),
    Arg('ext_csd_value', int, 'Expected value in ext_csd[ext_csd_index].'),
    Arg('manfid', str,
        'Specific Manufacturer ID to check. \n'
        'If we have multiple sources of eMMC, we may only want to apply '
        'this check for certain vendor.')
  ]

  def _GetFixedDevice(self, manfid):
    """Returns paths to all fixed storage devices on the system.

    Args:
      manfid: Expected manfid (Manufacturer ID)
    """
    ret = []

    for node in sorted(glob('/sys/class/block/*')):
      path = os.path.join(node, 'removable')
      if not os.path.exists(path) or open(path).read().strip() != '0':
        continue
      if re.match('^loop|^dm-', os.path.basename(node)):
        # Loopback or dm-verity device; skip
        continue
      path = os.path.join(node, 'device', 'manfid')
      if not os.path.exists(path) or open(path).read().strip() != manfid:
        continue
      ret.append(node)

    return ret

  def _ReadExtCSD(self, syspath, byte_index):
    """Reads a byte from EXT_CSD.

    Output of the command is like:

      EXT_CSD binary dump:
         0:   0:   00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
        16:  10:   00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
        32:  20:   00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
        ...

    Args:
      syspath: Device syspath.
      byte_index: Byte index.
    """
    base = byte_index & ~0xf
    offset = byte_index - base
    lines = GetLines(CheckOutput(['mmc', 'extcsd', 'dump',
                                  '/dev/' + os.path.basename(syspath)]),
                     strip=True)
    pattern = re.compile(r'^\s*(\d+):\s*\d+:\s*(.*)$')
    for line in lines:
      m = pattern.match(line)
      if m and int(m.group(1)) == base:
        return int(m.group(2).split(' ')[offset], 16)

    return None

  def runTest(self):
    failures = []
    nodes = self._GetFixedDevice(self.args.manfid)

    if len(nodes) == 0:
      logging.info('No eMMC device found matching manfid=%s. Skip the test.',
                   self.args.manfid)
    elif len(nodes) > 1:
      failures.append('Multiple eMMC devices found matching manfid=%s.' %
                      self.args.manfid)
    else:
      read_value = self._ReadExtCSD(nodes[0], self.args.ext_csd_index)
      if read_value != self.args.ext_csd_value:
        failures.append('EXT_CSD[%d] of %s reads %s, but expecting %s.' %
                        (self.args.ext_csd_index, nodes[0], hex(read_value),
                         hex(self.args.ext_csd_value)))
      else:
        logging.info('EXT_CSD[%d] of %s reads %s successfully.',
                     self.args.ext_csd_index, nodes[0], hex(read_value))

    if len(failures) > 0:
      raise FactoryTestFailure('\n'.join(failures))
