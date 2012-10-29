#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
import mox
import os
import re
import shutil
import tempfile
import threading
import time
import unittest
import yaml

from cros.factory import event_log

MAC_RE = re.compile(r'^([a-f0-9]{2}:){5}[a-f0-9]{2}$')
UUID_RE = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-'
                     '[a-f0-9]{4}-[a-f0-9]{12}$')


class BasicTest(unittest.TestCase):
  def testEventNameRE(self):
    for i in ('a', '_', 'azAZ09_', 'a0'):
      self.assertTrue(event_log.EVENT_NAME_RE.match(i))

    for i in ('', 'a.', '0', '0a'):
      self.assertFalse(event_log.EVENT_NAME_RE.match(i))


class GlobalSeqTest(unittest.TestCase):
  def setUp(self):
    self.path = tempfile.NamedTemporaryFile().name

  def tearDown(self):
    #os.unlink(self.path)
    #os.unlink(self.path + event_log.GlobalSeq.BACKUP_SUFFIX)
    pass

  def testSeq(self):
    def read_seq():
      return int(open(self.path).read() or '0')
    def read_seq_backup():
      return int(open(self.path + event_log.GlobalSeq.BACKUP_SUFFIX).read()
                 or '0')
    DELTA = event_log.GlobalSeq.BACKUP_SEQUENCE_INCREMENT

    seq1 = event_log.GlobalSeq(self.path)
    self.assertEquals(0, read_seq())
    self.assertEquals(0, read_seq_backup())
    self.assertEquals(0, seq1.Next())
    seq2 = event_log.GlobalSeq(self.path)
    self.assertEquals(1, seq2.Next())
    self.assertEquals(2, read_seq())
    self.assertEquals(2, read_seq_backup())
    self.assertEquals(2, seq1.Next())
    self.assertEquals(3, read_seq())
    self.assertEquals(3, read_seq_backup())

    # Disaster strikes!
    os.unlink(seq1.path)
    self.assertEquals(3 + DELTA, seq1.Next())
    self.assertEquals(4 + DELTA, read_seq())
    self.assertEquals(4 + DELTA, read_seq_backup())
    self.assertEquals(4 + DELTA, seq1.Next())
    self.assertEquals(5 + DELTA, read_seq())
    self.assertEquals(5 + DELTA, read_seq_backup())

    # Apocalyse strikes - both files are deleted!
    os.unlink(seq1.path)
    os.unlink(seq1.backup_path)

    mocker = mox.Mox()
    seq1._time = mocker.CreateMockAnything()
    seq1._time.time().AndReturn(1342422945.125)  # pylint: disable=W0212
    mocker.ReplayAll()
    self.assertEquals(1342422945125, seq1.Next())
    mocker.VerifyAll()
    self.assertEquals(1342422945126, read_seq())
    self.assertEquals(1342422945126, read_seq_backup())

  def _testThreads(self, after_read=lambda: True):
    '''Tests atomicity by doing operations in 20 threads for 1 sec.

    Args:
      after_read: See GlobalSeq._after_read.
    '''
    values = []

    start_time = time.time()
    end_time = start_time + 1

    def target():
      seq = event_log.GlobalSeq(self.path, _after_read=after_read)
      while time.time() < end_time:
        values.append(seq.Next())

    threads = [threading.Thread(target=target) for _ in xrange(20)]
    for t in threads:
      t.start()
    for t in threads:
      t.join()

    # After we sort, should be numbers [0, len(values)).
    values.sort()
    self.assertEquals(range(len(values)), values)
    return values

  def testThreadsWithSleep(self):
    values = self._testThreads(after_read=lambda: time.sleep(.1))
    # There should be about 20 values (1 every 50 ms for 1 s).
    # Significantly more or less than that and something went wrong.
    self.assertTrue(len(values) > 10, values)
    self.assertTrue(len(values) < 50, values)

  def testThreadsWithoutSleep(self):
    values = self._testThreads()
    # There should be lots of values (I get 2500 on my laptop); we'll
    # just make sure there are >100.
    self.assertTrue(len(values) > 100, values)


class EventLogTest(unittest.TestCase):
  def setUp(self):
    # Remove events directory and reset globals
    shutil.rmtree(event_log.EVENT_LOG_DIR, ignore_errors=True)
    event_log.device_id = event_log.image_id = None

    self.tmp = tempfile.mkdtemp()
    self.seq = event_log.GlobalSeq(os.path.join(self.tmp, 'seq'))

  def tearDown(self):
    shutil.rmtree(self.tmp)

  def testGetBootId(self):
    assert UUID_RE.match(event_log.GetBootId())

  def testGetDeviceId(self):
    device_id = event_log.GetDeviceId()
    assert (MAC_RE.match(device_id) or
            UUID_RE.match(device_id)), device_id

    # Remove device_id and make sure we get the same thing
    # back again, re-reading it from disk or the wlan0 interface
    event_log.device_id = None
    self.assertEqual(device_id, event_log.GetDeviceId())

    self.assertNotEqual(device_id, event_log.GetImageId())

  def testGetImageId(self):
    image_id = event_log.GetImageId()
    assert UUID_RE.match(image_id), image_id

    # Remove image_id and make sure we get the same thing
    # back again, re-reading it from disk
    event_log.image_id = None
    self.assertEqual(image_id, event_log.GetImageId())

    # Remove the image_id file; now we should get something
    # *different* back.
    event_log.image_id = None
    os.unlink(event_log.IMAGE_ID_PATH)
    self.assertNotEqual(image_id, event_log.GetImageId())

  def testSuppress(self):
    for suppress in [False, True]:
      log = event_log.EventLog('test', suppress=suppress)
      log.Log('test')
      self.assertEquals(not suppress, os.path.exists(log.path))

  def testEventLogDefer(self):
    self._testEventLog(True)

  def testEventLogNoDefer(self):
    self._testEventLog(False)

  def _testEventLog(self, defer):
    log = event_log.EventLog('test', defer=defer, seq=self.seq)
    self.assertEqual(os.path.exists(log.path), not defer)

    event0 = dict(a='A',
                  b=1,
                  c=[1,2],
                  d={'D1': 3, 'D2': 4},
                  e=['E1', {'E2': 'E3'}],
                  f=True,
                  g=u"[[[囧]]]".encode('utf-8'))
    log.Log('event0', **event0)
    log.Log('event1')
    log.Close()

    try:
      log.Log('should-fail')
      self.fail('Expected exception')
    except:  # pylint: disable=W0702
      pass

    log_data = list(yaml.load_all(open(log.path, "r")))
    self.assertEqual(4, len(log_data))

    for i in log_data[0:3]:
      # Check and remove times, to make everything else easier to compare
      assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$',
                      i['TIME']), i['TIME']
      del i['TIME']

    self.assertEqual(
      ['EVENT', 'SEQ', 'boot_id', 'boot_sequence', 'device_id',
       'factory_md5sum', 'filename', 'image_id', 'log_id'],
      sorted(log_data[0].keys()))
    self.assertEqual('preamble', log_data[0]['EVENT'])
    self.assertEqual(0, log_data[0]['SEQ'])
    self.assertEqual(event_log.GetBootId(), log_data[0]['boot_id'])
    self.assertEqual(-1, log_data[0]['boot_sequence'])
    self.assertEqual(event_log.GetDeviceId(), log_data[0]['device_id'])
    self.assertEqual(event_log.GetImageId(), log_data[0]['image_id'])
    self.assertEqual(os.path.basename(log.path), log_data[0]['filename'])
    self.assertEqual('test-' + log_data[0]['log_id'],
                     log_data[0]['filename'])

    event0.update(dict(EVENT='event0', SEQ=1))
    self.assertEqual(event0, log_data[1])
    self.assertEqual(dict(EVENT='event1', SEQ=2), log_data[2])
    self.assertEqual(None, log_data[3])

  def testDeferWithoutEvents(self):
    log = event_log.EventLog('test', defer=True, seq=self.seq)
    path = log.path
    log.Close()
    self.assertFalse(os.path.exists(path))

  def testBootSequence(self):
    try:
      os.unlink(event_log.BOOT_SEQUENCE_PATH)
    except OSError:
      pass

    for i in xrange(-1, 5):
      self.assertEqual(i, event_log.GetBootSequence())
      event_log.IncrementBootSequence()
      self.assertEqual(str(i + 1),
                       open(event_log.BOOT_SEQUENCE_PATH).read())

if __name__ == "__main__":
  unittest.main()
