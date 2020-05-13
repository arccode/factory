# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Performs consecutive read/write operations on a single file.

Description
-----------
This pytest performs consecutive read/write operations on a single file under a
specific directory or mount point. The primary purpose is to keep storage busy
for some reliability test. It can also be used as a simple approach to stress a
storage device as well.

Since it operates on a single file under user space, controls over which block
is exercising are limited (e.g., it might always write on the same block.)
In this sense, this test should be considered as a test with limited coverage.

Also noted that, an unexpected abortion will leave the temporary file uncleaned
in the specified directory or mount point.

Please also refer to the pytest `removable_storage`, which might also be useful
to test a storage device.

Test Procedure
--------------
This is an automated test without user interaction.

Dependency
----------
Use `toybox` and `dd` to perform read/write operations.
Use `/dev/urandom` to generate random data for write.

Examples
--------
To test read/write a 10MB file under `/home/root`, add this in test list::

  {
    "pytest_name": "storage_simple_stress",
    "args": {
      "operations": 1,
      "dir": "/home/root",
      "file_size": 10485760
    }
  }

To test read/write of a 100MB file 3 times for block device 'mmcblk1p1'::

  {
    "pytest_name": "storage_simple_stress",
    "args": {
      "operations": 3,
      "mount_device": "/dev/block/mmcblk1p1",
      "dir": ".",
      "file_size": 104857600
    }
  }
"""

import logging
import time
import unittest

from cros.factory.device import device_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sys_utils

BLOCK_SIZE = 4096


class SimpleStorageStressTest(unittest.TestCase):

  ARGS = [
      Arg('dir', str, 'Directory for creating files for random access.'),
      Arg('file_size', int,
          'The file size of generated file.'),
      Arg('operations', int,
          'The number of operations to perform.'),
      Arg('mount_device', str, 'If not None, we mount the given device first '
          'to a temp directory, and perform reading / writing under the '
          "directory. The arugment 'dir' will be used as the relative path "
          'under the mount point.', default=None),
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()

  def ReadWriteFile(self, test_file, file_size):
    """Performs a read/write to a specific file."""

    with self._dut.temp.TempFile() as data_file:
      # Prepare a random content.
      logging.info('Preparing data.')
      self._dut.CheckCall(
          ['toybox', 'dd', 'if=/dev/urandom',
           'of=%s' % data_file, 'bs=%d' % file_size,
           'count=1', 'conv=sync'])

      # perform write operation.
      logging.info('Performing write test.')
      start_time = time.time()
      self._dut.CheckCall(
          ['toybox', 'dd', 'if=%s' % data_file, 'of=%s' % test_file,
           'bs=%d' % BLOCK_SIZE, 'conv=fsync'])
      write_time = time.time() - start_time

      # Drop cache to ensure the system do a real read.
      logging.debug('Memory usage before drop_caches = %s',
                    self._dut.CheckOutput(['free', '-m']))
      # For the constant, please refer to 'man drop_caches'
      self._dut.WriteFile('/proc/sys/vm/drop_caches', '3')
      logging.debug('Memory usage after drop_caches = %s',
                    self._dut.CheckOutput(['free', '-m']))

      # perform read operation.
      logging.info('Performing read test.')
      start_time = time.time()
      self._dut.CheckCall(
          'toybox dd if=%s | toybox cmp %s -' % (test_file, data_file))
      read_time = time.time() - start_time

      logging.info('Write time=%.3f secs', write_time)
      logging.info('Read time=%.3f secs', read_time)
      return True

  def TestReadWriteIn(self, dirpath):
    file_size = self.args.file_size
    for iteration in range(self.args.operations):
      with self._dut.temp.TempFile(dir=dirpath) as temp_file:
        logging.info(
            '[%d/%d]: Tempfile[%s] created for %d bytes write/read test',
            iteration, self.args.operations, temp_file, file_size)
        self.ReadWriteFile(temp_file, file_size)

  def runTest(self):
    if self.args.mount_device:
      with sys_utils.MountPartition(
          self.args.mount_device, rw=True, dut=self._dut) as mount_path:
        self.TestReadWriteIn(self._dut.path.join(mount_path, self.args.dir))
    else:
      self.TestReadWriteIn(self.args.dir)
