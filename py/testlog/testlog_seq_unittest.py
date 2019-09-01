#!/usr/bin/env python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for testlog_seq.py."""


import json
import logging
import os
import shutil
import tempfile
import threading
import time
import unittest

from testlog_pkg import testlog_seq
from testlog_pkg.utils import file_utils


class BootSequenceTest(unittest.TestCase):
  """Unittests for SeqGenerator."""

  def setUp(self):
    self.tmp = tempfile.mkdtemp(prefix='BootSeqTest.')
    self.seq_path = os.path.join(self.tmp, 'seq_test')
    self.json_path = os.path.join(self.tmp, 'json_test')

  def tearDown(self):
    shutil.rmtree(self.tmp)

  def testSimulateReboot(self):
    """Tests seq recovery functionality.  Should use the maximum seq."""
    first_seq = 1986
    last_seq = 1105
    with open(self.json_path, 'w') as fd:
      fd.write(json.dumps({'seq': first_seq}) + '\n')
      fd.write(json.dumps({'seq': last_seq}) + '\n')

    seq = testlog_seq.SeqGenerator(self.seq_path, self.json_path)
    next_seq = seq.Next()
    current_seq = seq.Current()
    self.assertEquals(next_seq, current_seq)
    # pylint: disable=protected-access
    self.assertEquals(
        next_seq, 1 + first_seq + testlog_seq.SEQ_INCREMENT_ON_BOOT)

  def testAllCorrupt(self):
    """Tests seq recovery functionality.  Should use current time."""
    with open(self.json_path, 'w') as fd:
      fd.write('corrupt\n')
      fd.write('corrupt\n')
      fd.write('\0' * 100)
    seq = testlog_seq.SeqGenerator(self.seq_path, self.json_path)
    next_seq = seq.Next()
    cur_time = int(time.time() * 1000)
    self.assertAlmostEqual(next_seq, cur_time, delta=1000)

  def testSomeCorrupt(self):
    """Tests seq recovery functionality.

    Should recover from biggest seq value."""
    last_seq = 1105
    last_valid_seq = last_seq - 10
    with open(self.json_path, 'w') as fd:
      fd.write('\0' * 100)  # corrupt before last valid line should be ignored
      for i in reversed(xrange(5)):
        fd.write(json.dumps({'seq': last_valid_seq - i}) + '\n')
      # last_seq is invalid because this line begins with '\0'
      fd.write('\0' * 100)
      fd.write(json.dumps({'seq': last_seq}) + '\n')
      fd.write('corrupt\n')
      fd.write('corrupt\n')
      fd.write('\0' * 100)
    seq = testlog_seq.SeqGenerator(self.seq_path, self.json_path)
    next_seq = seq.Next()
    self.assertEquals(
        next_seq, 1 + last_valid_seq + testlog_seq.SEQ_INCREMENT_ON_BOOT)

  def testFailsWhenLocked(self):
    seq = testlog_seq.SeqGenerator(self.seq_path, self.json_path)
    with file_utils.FileLock(self.seq_path):
      with self.assertRaises(file_utils.FileLockTimeoutError):
        seq.Next()
      with self.assertRaises(file_utils.FileLockTimeoutError):
        seq.Current()

  def testBasic(self):
    with open(self.json_path, 'w') as fd:
      # The context of JSON file for recovery is empty.
      seq = testlog_seq.SeqGenerator(self.seq_path, fd.name)
      for i in range(3):
        self.assertEquals(i, seq.Next())
      del seq

      # Test if it will read out the existing seq file.
      seq = testlog_seq.SeqGenerator(self.seq_path, fd.name)
      for i in range(3, 6):
        self.assertEquals(i, seq.Next())

  def _testThreads(self, after_read=lambda: True, filelock_waitsecs=1.0):
    """Tests atomicity by doing operations in 10 threads for 1 sec.

    Args:
      after_read: See GlobalSeq._after_read.
    """
    values = []

    start_time = time.time()
    end_time = start_time + 1

    def target():
      seq = testlog_seq.SeqGenerator(
          self.seq_path, self.json_path, _after_read=after_read,
          _filelock_waitsecs=filelock_waitsecs)
      while time.time() < end_time:
        values.append(seq.Next())

    threads = [threading.Thread(target=target) for _ in xrange(10)]
    for t in threads:
      t.start()
    for t in threads:
      t.join()

    # After we sort, should be numbers [1, len(values)].
    values.sort()
    self.assertEquals(range(len(values)), values)
    return values

  def testThreadsWithSleep(self):
    values = self._testThreads(after_read=lambda: time.sleep(.05),
                               filelock_waitsecs=2.0)
    logging.info('testThreadsWithSleep exercises %d writes', len(values))
    # There should be about 20 to 30 values (1 every 50 ms for 1 s
    # plus a number less than the number of threads). Notice that
    # seq file is locked even for the threads in same process.
    # Significantly more or less than that and something went wrong.
    self.assertTrue(len(values) > 10, values)
    self.assertTrue(len(values) < 30, values)

  def testThreadsWithoutSleep(self):
    values = self._testThreads(filelock_waitsecs=2.0)
    logging.info('testThreadsWithoutSleep exercises %d writes', len(values))
    # There should be lots of values (I get over 15000 on my desktop); we'll
    # just make sure there are >1000.
    self.assertTrue(len(values) > 1000, values)

if __name__ == '__main__':
  logging.basicConfig(
      format=('[%(levelname)s] '
              ' %(threadName)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=logging.INFO,
      datefmt='%Y-%m-%d %H:%M:%S')
  unittest.main()
