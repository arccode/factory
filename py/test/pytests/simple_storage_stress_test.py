# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Performs consecutive read/write operations.

This is a factory test to perform consecutive read/write operations of a single
file under a specific directory. The primary purpose is to keep storage busy
which is required by some reliability test. It can be used as a simple approach
to stress a storage device as well.

Since it operates on a single file under user space, controls over which block
is exercising are limited (i.e: it might always writing the same block.)
Should be considered as a test with limited coverage.

In addition, unexpected abortion will leave the temporary file uncleaned in the
specified directory.
"""

import logging
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import dut
from cros.factory.test.args import Arg
from cros.factory.test.utils.mount_utils import Mount

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
    self._dut = dut.Create()

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
    for iteration in xrange(self.args.operations):
      with self._dut.temp.TempFile(dir=dirpath) as temp_file:
        logging.info(
            '[%d/%d]: Tempfile[%s] created for %d bytes write/read test',
            iteration, self.args.operations, temp_file, file_size)
        self.ReadWriteFile(temp_file, file_size)

  def runTest(self):
    if self.args.mount_device:
      with self._dut.temp.TempDirectory() as mount_path:
        with Mount(self._dut, self.args.mount_device, mount_path):
          self.TestReadWriteIn(self._dut.path.join(mount_path, self.args.dir))
    else:
      self.TestReadWriteIn(self.args.dir)
