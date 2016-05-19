#!/usr/bin/python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for log_writer.py."""


import json
import os
import Queue
import threading
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import log_writer
from cros.factory.utils import file_utils


def Reset():
  """Deletes state files and resets global variables."""
  # pylint: disable=W0212
  log_writer._device_id = log_writer._reimage_id = None
  log_writer._global_log_writer = None

  for f in [log_writer.DEVICE_ID_PATH, log_writer.REIMAGE_ID_PATH,
            log_writer.INIT_COUNT_PATH, log_writer.TESTLOG_PATH,
            log_writer.SEQUENCE_PATH]:
    file_utils.TryUnlink(f)


class MockEvent(object):
  def __init__(self, string):
    self.data = {'$string': string}
    self.seq = None

  def Populate(self, data):
    self.data.update(data)
    self.seq = data.pop('seq', self.seq)

  def ToJSON(self):
    """Format an ad-hoc string as a JSON event for testing."""
    return json.dumps(self.data)


class LogWriterTest(unittest.TestCase):
  """Unittests for LogWriter."""

  def setUp(self):
    Reset()

  def testRecoverSeq(self):
    """Test seq recovery functionality."""
    writer = log_writer.LogWriter()
    writer.Log(MockEvent('event0'))  # event 0
    writer.Log(MockEvent('event1'))  # event 1
    writer.Log(MockEvent('event2'))  # event 2

    # Delete the sequence file to simulate corruption.
    os.unlink(log_writer.SEQUENCE_PATH)

    writer.Log(MockEvent('event3'))

    line = None
    for line in open(log_writer.TESTLOG_PATH):
      pass
    seq = json.loads(line)['seq']

    # Sequence file should be re-created, starting with 3 plus
    # SEQ_INCREMENT_ON_BOOT.
    self.assertEquals(seq, 3 + log_writer.SEQ_INCREMENT_ON_BOOT)

  def testIds(self):
    """Test that IDs are properly getting set."""
    test_run_id = 'bfa88756-ef2b-4e58-a4a2-eda1408bc93f'
    log_writer.GetDeviceID()
    log_writer.GetReimageID()

    writer = log_writer.LogWriter(test_run_id=test_run_id)
    event = MockEvent('event0')
    writer.Log(event)
    self.assertEquals(event.data['testRunId'], test_run_id)
    self.assertEquals(event.data['stationDeviceId'], log_writer.GetDeviceID())
    self.assertEquals(event.data['stationReimageId'], log_writer.GetReimageID())


class JSONLogFileTest(unittest.TestCase):
  """Unittests for JSONLogFile."""

  def setUp(self):
    Reset()

  def testRecoverSeq(self):
    """Test that RecoverSeq is returning the proper value."""
    json_log = log_writer.JSONLogFile()
    self.assertEquals(json_log.RecoverSeq(), 0)
    json_log.Log('corrupted_data\n')
    self.assertEquals(json_log.RecoverSeq(), None)
    json_log.Log('{"seq": 3333}\n')
    self.assertEquals(json_log.RecoverSeq(), 3334)

  def testLock(self):
    """Test reentrant file lock functionality."""
    json1 = log_writer.JSONLogFile()
    # pylint: disable=W0212
    json1._OpenUnlocked()
    json2 = log_writer.JSONLogFile()
    json2._OpenUnlocked()
    self.assertNotEquals(json1.file.fileno(), json2.file.fileno())

    recovered_seq = Queue.Queue()
    def GetRecoverSeq():
      with json1:
        recovered_seq.put(json1.RecoverSeq())

    t = threading.Thread(target=GetRecoverSeq)
    with json2:
      t.start()
      for i in range(5):
        event = MockEvent('test')
        event.Populate({'seq': i})
        json2.Log(event.ToJSON() + '\n')
        time.sleep(1)

    t.join()
    self.assertEquals(recovered_seq.get(), 5)


class GlobalSeqTest(unittest.TestCase):
  """Unittests for GlobalSeq."""

  def setUp(self):
    Reset()

  def testBasic(self):
    seq = log_writer.GlobalSeq()
    for i in range(3):
      self.assertEquals(i, seq.Next())
    del seq

    # Try again with a new sequence file
    seq = log_writer.GlobalSeq()
    for i in range(3, 6):
      self.assertEquals(i, seq.Next())
    del seq

  def testMissingSequenceFile(self):
    json_log = log_writer.JSONLogFile()

    # Generate a few sequence numbers.
    seq = log_writer.GlobalSeq(recovery_fn=json_log.RecoverSeq)
    self.assertEquals(0, seq.Next())
    self.assertEquals(1, seq.Next())
    # Log an event; will have sequence number 2.
    log_writer.LogWriter().Log(MockEvent('bar'))
    with open(log_writer.TESTLOG_PATH) as f:
      assert '"seq": 2' in f.readline()

    # Delete the sequence file to simulate corruption.
    os.unlink(log_writer.SEQUENCE_PATH)
    # Sequence file should be re-created, starting with 3 plus
    # SEQ_INCREMENT_ON_BOOT.
    self.assertEquals(3 + log_writer.SEQ_INCREMENT_ON_BOOT,
                      seq.Next())

    # Delete the sequence file and create a new GlobalSeq object to
    # simulate a reboot. We'll do this a few times.
    for i in range(3):
      # Log an event to record the new sequence number for "reboot"
      log_writer.LogWriter().Log(MockEvent('bar'))

      del seq
      os.unlink(log_writer.SEQUENCE_PATH)
      seq = log_writer.GlobalSeq(recovery_fn=json_log.RecoverSeq)
      # Sequence file should be re-created, increasing by 1 for the logged
      # event, and SEQ_INCREMENT_ON_BOOT for the reboot.
      self.assertEquals(
          5 + (i * 2) + (i + 2) * log_writer.SEQ_INCREMENT_ON_BOOT,
          seq.Next())

  def _testThreads(self, after_read=lambda: True):
    """Tests atomicity by doing operations in 10 threads for 1 sec.

    Args:
      after_read: See GlobalSeq._after_read.
    """
    values = []

    start_time = time.time()
    end_time = start_time + 1

    def target():
      seq = log_writer.GlobalSeq(_after_read=after_read)
      while time.time() < end_time:
        values.append(seq.Next())

    threads = [threading.Thread(target=target) for _ in xrange(10)]
    for t in threads:
      t.start()
    for t in threads:
      t.join()

    # After we sort, should be numbers [1 .. len(values)].
    values.sort()
    self.assertEquals(range(len(values)), values)
    return values

  def testThreadsWithSleep(self):
    values = self._testThreads(after_read=lambda: time.sleep(.05))
    # There should be about 20 to 30 values (1 every 50 ms for 1 s, plus
    # a number less than the number of threads).
    # Significantly more or less than that and something went wrong.
    self.assertTrue(len(values) > 10, values)
    self.assertTrue(len(values) < 30, values)

  def testThreadsWithoutSleep(self):
    values = self._testThreads()
    # There should be lots of values (I get over 10000 on my desktop); we'll
    # just make sure there are >1000.
    self.assertTrue(len(values) > 1000, values)

  def testOutOfOrderThreads(self):
    """Check that events are written down to the JSON log file in order."""
    def LogThread(thread_name, sleep_time, iterations=10):
      seq = log_writer.GlobalSeq(_after_write=lambda: time.sleep(sleep_time))
      lw = log_writer.LogWriter(seq=seq)
      for i in xrange(iterations):
        lw.Log(MockEvent('{}: {}'.format(thread_name, i)))

    threads = [threading.Thread(
        target=LogThread,
        args=('p{}'.format(i), 0.01 * i)) for i in xrange(5)]
    for t in threads:
      t.start()
    for t in threads:
      t.join()

    # Collect the events from the JSON log.
    f = open(log_writer.TESTLOG_PATH, 'r')
    last_seq = -1
    for line in f:
      seq = json.loads(line)['seq']
      self.assertEquals(last_seq + 1, seq)
      last_seq = seq

  def _testGetIDLock(self, fn):
    # 50 seemed like the necessary threshold to get this to fail most of
    # the time.
    ids = None
    for _ in xrange(50):
      Reset()
      ids = set()
      def AddID():
        ids.add(fn())

      threads = [threading.Thread(target=AddID) for _ in xrange(3)]
      for t in threads:
        t.start()
      for t in threads:
        t.join()

      self.assertEqual(len(ids), 1)

  def testDeviceIDLock(self):
    self._testGetIDLock(log_writer.GetDeviceID)

  def testReimageIDLock(self):
    self._testGetIDLock(log_writer.GetReimageID)


class GlobalLogWriterTest(unittest.TestCase):
  """Unittests for GetGlobalLogWriter."""

  def setUp(self):
    # Reset the global log writer.
    log_writer._global_log_writer = None  # pylint: disable=W0212

    if 'CROS_FACTORY_TEST_PARENT_INVOCATION' in os.environ:
      del os.environ['CROS_FACTORY_TEST_PARENT_INVOCATION']

  def testGlobalInstanceNoEnv(self):
    writer = log_writer.GetGlobalLogWriter()
    self.assertEqual(None, writer.test_run_id)

  def testGlobalInstanceWithEnv(self):
    stub_uuid = 'bfa88756-ef2b-4e58-a4a2-eda1408bc93f'
    os.environ['CROS_FACTORY_TEST_PARENT_INVOCATION'] = stub_uuid

    writer = log_writer.GetGlobalLogWriter()
    self.assertEqual(stub_uuid, writer.test_run_id)

  def testSingleton(self):
    # pylint: disable=W0212
    self.assertEquals(None, log_writer._global_log_writer)
    writer1 = log_writer.GetGlobalLogWriter()
    writer2 = log_writer.GetGlobalLogWriter()
    self.assertTrue(writer1 is writer2)

  def testClose(self):
    writer = log_writer.GetGlobalLogWriter()
    writer.Close()


if __name__ == '__main__':
  unittest.main()
