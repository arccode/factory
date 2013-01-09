# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''Verifies the integrity of the root partition.'''

import logging
import os
import re
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.args import Arg
from cros.factory.utils.process_utils import Spawn

DM_DEVICE_NAME = 'verifyroot'
DM_DEVICE_PATH = os.path.join('/dev/mapper', DM_DEVICE_NAME)
BLOCK_SIZE = 8*1024*1024

class VerifyRootPartitionTest(unittest.TestCase):
  ARGS = [
      Arg('kern_a_device', str, 'Device containing KERN-A partition',
          default='sda4'),
      Arg('root_device', str, 'Device containing root partition',
          default='sda5'),
      Arg('max_bytes', int, 'Maximum number of bytes to read', optional=True),
      ]

  def runTest(self):
    # Copy out the KERN-A partition to a file, since vbutil_kernel
    # won't operate on a device, only a file
    # (http://crosbug.com/34176)
    with tempfile.NamedTemporaryFile() as kern_a_bin:
      with open('/dev/%s' % self.args.kern_a_device) as kern_a:
        shutil.copyfileobj(kern_a, kern_a_bin)
      kern_a_bin.flush()
      vbutil_kernel = Spawn(
          ['vbutil_kernel', '--verify', kern_a_bin.name, '--verbose'],
          log=True, read_stdout=True)
      self.assertEqual(
          0, vbutil_kernel.returncode,
          ('Unable to verify kernel in KERN-A; perhaps this device was imaged '
           'with chromeos-install instead of mini-Omaha server?'))

    logging.info('vbutil_kernel output is:\n%s', vbutil_kernel.stdout_data)

    DM_REGEXP = re.compile(r'dm="(?:1 )?vroot none ro(?: 1)?,(0 (\d+) .+)"')
    match = DM_REGEXP.search(vbutil_kernel.stdout_data)
    assert match, 'Cannot find regexp %r in vbutil_kernel output' % (
        DM_REGEXP.pattern)

    table = match.group(1)
    partition_size = int(match.group(2)) * 512

    assert '%U+1' in table
    table = table.replace('%U+1', '/dev/%s' % self.args.root_device)
    # Cause I/O error on invalid bytes
    table += ' error_behavior=eio'

    # Remove device in case a previous test left it hanging
    self._RemoveDMDevice()
    assert not os.path.exists(DM_DEVICE_PATH)
    # Map the device
    Spawn(['dmsetup', 'create', '-r', DM_DEVICE_NAME, '--table',
           table], check_call=True, log=True, log_stderr_on_error=True)

    # Read data from the partition; there will be an I/O error on failure
    if self.args.max_bytes is None:
      bytes_to_read = partition_size
    else:
      bytes_to_read = min(partition_size, self.args.max_bytes)

    with open(DM_DEVICE_PATH) as dm_device:
      bytes_read = 0
      while True:
        bytes_left = bytes_to_read - bytes_read
        if not bytes_left:
          break
        count = len(dm_device.read(min(BLOCK_SIZE, bytes_left)))
        if not count:
          break
        bytes_read += count
        logging.info('Read %s bytes (%.1f%%)',
            bytes_read, bytes_read * 100. / bytes_to_read)
    self.assertEquals(bytes_to_read, bytes_read)

  def tearDown(self):
    self._RemoveDMDevice()

  def _RemoveDMDevice(self):
    Spawn(['dmsetup', 'remove', DM_DEVICE_NAME], log=True, call=True)
