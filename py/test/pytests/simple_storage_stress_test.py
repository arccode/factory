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
import os
import tempfile
import time
import unittest

from cros.factory.test import utils
from cros.factory.test.args import Arg

BLOCK_SIZE = 4096


class StartTest(unittest.TestCase):

  ARGS = [
    Arg('dir', str, 'Directory for creating files for random access'),
    Arg('file_size', int,
        'The file size of generated file'),
    Arg('operations', int,
        'The number of operations to perform')
  ]

  def ReadWriteFile(self, file_obj, file_size):
    '''Performs a read/write to a specific file descriptor.'''
    # Prepare a random content
    random_content = os.urandom(BLOCK_SIZE)

    # perform write operation.
    start_time = time.time()
    file_obj.seek(0)
    remaining_bytes = file_size
    while remaining_bytes > 0:
      if remaining_bytes >= BLOCK_SIZE:
        file_obj.write(random_content)
      else:
        file_obj.write(random_content[:remaining_bytes])
      remaining_bytes -= BLOCK_SIZE
    os.fsync(file_obj.fileno())
    write_time = time.time() - start_time

    # Drop cache to ensure the system do a real read.
    logging.debug('Memory usage before drop_caches = %s',
                  utils.CheckOutput(['free', '-m']))
    # For the constant, please refer to 'man drop_caches'
    with open('/proc/sys/vm/drop_caches', 'w') as f:
      f.write('3')
    logging.debug('Memory usage after drop_caches = %s',
                  utils.CheckOutput(['free', '-m']))

    # perform read operation.
    start_time = time.time()
    file_obj.seek(0)
    remaining_bytes = file_size
    while remaining_bytes > 0:
      size = min(remaining_bytes, BLOCK_SIZE)
      self.assertEquals(random_content[:size], file_obj.read(size))
      remaining_bytes -= size
    read_time = time.time() - start_time

    logging.info('Write time=%.3f secs', write_time)
    logging.info('Read time=%.3f secs', read_time)
    return True

  def runTest(self):
    file_size = self.args.file_size
    for iteration in xrange(self.args.operations):
      with tempfile.NamedTemporaryFile(dir=self.args.dir) as temp_file:
        logging.info(
          '[%d/%d]: Tempfile[%s] created for %d bytes write/read test',
          iteration, self.args.operations, temp_file.name, file_size)
        self.ReadWriteFile(temp_file, file_size)
