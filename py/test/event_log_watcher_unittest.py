#!/usr/bin/env python2
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import tempfile
import time
import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.test import event_log
from cros.factory.test import event_log_watcher
from cros.factory.test.event_log_watcher import Chunk
from cros.factory.test.event_log_watcher import EventLogWatcher

MOCK_LOG_NAME = lambda x: 'mylog12345%d' % x


def MOCK_PREAMBLE(x, sync_marker=False):
  ret = 'device: 123%d\nimage: 456\nmd5: abc\n' % x
  if sync_marker:
    ret += event_log.SYNC_MARKER
  ret += '---\n'
  return ret


def MOCK_EVENT(x=0, sync_marker=False):
  ret = 'seq: %d\nevent: start\n' % x
  if sync_marker:
    ret += event_log.SYNC_MARKER
  ret += '---\n'
  return ret
MOCK_PERIOD = 0.01


class ChunkTest(unittest.TestCase):

  def testStr(self):
    self.assertEquals("Chunk(log_name='a', len=3, pos=10)",
                      str(Chunk('a', 'foo', 10)))


class EventLogWatcherTest(unittest.TestCase):

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()
    self.events_dir = os.path.join(self.temp_dir, 'events')
    os.mkdir(self.events_dir)
    self.db = os.path.join(self.temp_dir, 'db')

  def tearDown(self):
    # Remove temp event log files and db files.
    shutil.rmtree(self.temp_dir)

  def WriteLog(self, content, file_name=None):
    """Writes text content into a log file.

    If the given log file exists, new content will be appended.

    Args:
      content: the text content to write
      file_name: the name of the log file we're written to
    """
    file_path = ''
    if file_name is None:
      file_path = tempfile.NamedTemporaryFile(dir=self.events_dir,
                                              delete=False).name
    else:
      file_path = os.path.join(self.events_dir, file_name)
    with open(file_path, 'a') as f:
      f.write(content)

  def testWatchThread(self):
    class Handler(object):
      handled = False

      def __init__(self):
        pass

      def handle_cb(self, chunk_infos, periodic):
        self.handled = True
    h = Handler()

    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db,
                              h.handle_cb)
    watcher.StartWatchThread()
    self.WriteLog(MOCK_PREAMBLE(0))

    # Assert handle_cb has ever been called in 2 seconds.

    for _ in range(200):
      if h.handled:
        break
      time.sleep(MOCK_PERIOD)
    else:
      self.fail()

    watcher.FlushEventLogs()
    watcher.StopWatchThread()

  def testWatch(self):
    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db)

    self.WriteLog(MOCK_PREAMBLE(0), MOCK_LOG_NAME(0))

    # Assert nothing stored yet before scan.
    self.assertEqual(watcher.GetEventLog(MOCK_LOG_NAME(0)), None)

    watcher.ScanEventLogs()

    log = watcher.GetEventLog(MOCK_LOG_NAME(0))
    self.assertNotEqual(log[event_log_watcher.KEY_OFFSET], 0)

    # Write more logs and flush.
    self.WriteLog(MOCK_EVENT(), MOCK_LOG_NAME(0))
    watcher.FlushEventLogs()

    log = watcher.GetEventLog(MOCK_LOG_NAME(0))
    self.assertEqual(log[event_log_watcher.KEY_OFFSET],
                     len(MOCK_PREAMBLE(0)) + len(MOCK_EVENT()))

    watcher.Close()

  def testCorruptDb(self):
    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db)

    self.WriteLog(MOCK_PREAMBLE(0), MOCK_LOG_NAME(0))

    # Assert nothing stored yet before flush.
    watcher.ScanEventLogs()
    self.assertNotEqual(watcher.GetEventLog(MOCK_LOG_NAME(0)), 0)

    # Manually truncate db file.
    with open(self.db, 'w') as f:
      os.ftruncate(file.fileno(f), 10)

    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db)
    self.assertEqual(watcher.GetEventLog(MOCK_LOG_NAME(0)), None)

  def testHandleEventLogsCallback(self):
    mock = mox.MockAnything()
    mock.handle_event_log([
        Chunk(MOCK_LOG_NAME(0), MOCK_PREAMBLE(0), 0)], False)
    mox.Replay(mock)

    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db,
                              mock.handle_event_log)

    self.WriteLog(MOCK_PREAMBLE(0), MOCK_LOG_NAME(0))
    watcher.ScanEventLogs()

    # Assert that the new log has been marked as handled.
    log = watcher.GetEventLog(MOCK_LOG_NAME(0))
    self.assertEqual(log[event_log_watcher.KEY_OFFSET],
                     len(MOCK_PREAMBLE(0)))

    mox.Verify(mock)

  def testHandleEventLogsCallbackMultiple(self):
    mock = mox.MockAnything()
    mock.handle_event_log(mox.IgnoreArg(), False)
    mock.handle_event_log(mox.IgnoreArg(), False)
    mox.Replay(mock)

    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db,
                              mock.handle_event_log, num_log_per_callback=2)

    for i in xrange(3):
      self.WriteLog(MOCK_PREAMBLE(i), MOCK_LOG_NAME(i))
    watcher.ScanEventLogs()

    # Assert that the new log has been marked as handled.
    for i in xrange(3):
      log = watcher.GetEventLog(MOCK_LOG_NAME(i))
      self.assertEqual(log[event_log_watcher.KEY_OFFSET],
                       len(MOCK_PREAMBLE(i)))

    mox.Verify(mock)

  def testHandleEventLogsCallbackUnlimited(self):
    mock = mox.MockAnything()
    mock.handle_event_log(mox.IgnoreArg(), False)
    mox.Replay(mock)

    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db,
                              mock.handle_event_log, num_log_per_callback=0)

    for i in xrange(3):
      self.WriteLog(MOCK_PREAMBLE(i), MOCK_LOG_NAME(i))
    watcher.ScanEventLogs()

    # Assert that the new log has been marked as handled.
    for i in xrange(3):
      log = watcher.GetEventLog(MOCK_LOG_NAME(i))
      self.assertEqual(log[event_log_watcher.KEY_OFFSET],
                       len(MOCK_PREAMBLE(i)))

    mox.Verify(mock)

  def testSyncMarkers_NoRestart(self):
    self._testSyncMarkers(False)

  def testSyncMarkers_Restart(self):
    self._testSyncMarkers(True)

  def _testSyncMarkers(self, unexpected_restart):
    # pylint: disable=not-callable
    m = mox.Mox()
    mock_callback = m.CreateMockAnything()
    path = os.path.join(self.events_dir, MOCK_LOG_NAME(0))

    # No DB; use sync markers.
    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, None,
                              mock_callback)
    self.WriteLog(MOCK_PREAMBLE(0, True), MOCK_LOG_NAME(0))

    mock_callback([
        Chunk(MOCK_LOG_NAME(0), MOCK_PREAMBLE(0, True), 0)], False)
    m.ReplayAll()
    watcher.ScanEventLogs()
    m.VerifyAll()

    def ReplaceSyncMarker(s):
      return s.replace(event_log.SYNC_MARKER_SEARCH,
                       event_log.SYNC_MARKER_REPLACE)

    # We should have replaced '#s' with '#S' in the preamble.
    self.assertEqual(ReplaceSyncMarker(MOCK_PREAMBLE(0, True)),
                     open(path).read())

    if unexpected_restart:
      # Re-create the event log watcher to zap its state.
      watcher.Close()
      watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, None,
                                mock_callback)
      # The event log watcher has forgotten about the file.
      self.assertIsNone(watcher.GetEventLog(MOCK_LOG_NAME(0)))
    else:
      # The event log watcher has the correct sync offset for the file.
      self.assertEquals(
          {event_log_watcher.KEY_OFFSET: len(MOCK_PREAMBLE(0, True))},
          watcher.GetEventLog(MOCK_LOG_NAME(0)))

    # Write two events; they (but not the preamble) should be scanned.
    self.WriteLog(MOCK_EVENT(0, True), MOCK_LOG_NAME(0))
    self.WriteLog(MOCK_EVENT(1, True), MOCK_LOG_NAME(0))
    m.ResetAll()
    mock_callback([
        Chunk(MOCK_LOG_NAME(0), MOCK_EVENT(0, True) + MOCK_EVENT(1, True),
              len(MOCK_PREAMBLE(0, True)))], False)
    m.ReplayAll()
    watcher.ScanEventLogs()
    m.VerifyAll()

    # We should have replaced '#s' with '#S' in the preamble and the
    # second real event.
    self.assertEqual(ReplaceSyncMarker(MOCK_PREAMBLE(0, True)) +
                     MOCK_EVENT(0, True) +
                     ReplaceSyncMarker(MOCK_EVENT(1, True)),
                     open(path).read())

  def testHandleEventLogsFail(self):
    mock = mox.MockAnything()
    mock.handle_event_log(
        [Chunk(MOCK_LOG_NAME(0), MOCK_PREAMBLE(0), 0)], False
    ).AndRaise(Exception('Bar'))
    mox.Replay(mock)
    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db,
                              mock.handle_event_log)

    self.WriteLog(MOCK_PREAMBLE(0), MOCK_LOG_NAME(0))
    watcher.ScanEventLogs()

    # Assert that watcher did not update the new event as uploaded
    # when handle logs fail.
    log = watcher.GetEventLog(MOCK_LOG_NAME(0))
    self.assertEqual(log[event_log_watcher.KEY_OFFSET], 0)
    mox.Verify(mock)

    watcher.Close()

  def testFlushEventLogsFail(self):
    mock = mox.MockAnything()
    mock.handle_event_log(
        [(MOCK_LOG_NAME(0), MOCK_PREAMBLE(0))], False).AndRaise(
            Exception('Foo'))
    mox.Replay(mock)
    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db,
                              mock.handle_event_log)

    self.WriteLog(MOCK_PREAMBLE(0), MOCK_LOG_NAME(0))

    # Assert exception caught.
    self.assertRaises(event_log_watcher.ScanException, watcher.FlushEventLogs)

    # Assert that watcher did not update the new event as uploaded
    # when handle logs fail.
    log = watcher.GetEventLog(MOCK_LOG_NAME(0))
    self.assertEqual(log[event_log_watcher.KEY_OFFSET], 0)
    mox.Verify(mock)

  def testIncompleteLog(self):
    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db)

    # Write the first line of mock preamble as incomplete event log.
    self.WriteLog(MOCK_PREAMBLE(0)[:13], MOCK_LOG_NAME(0))
    watcher.ScanEventLogs()

    # Incomplete preamble should be ignored.
    log = watcher.GetEventLog(MOCK_LOG_NAME(0))
    self.assertEqual(log[event_log_watcher.KEY_OFFSET], 0)

    self.WriteLog(MOCK_PREAMBLE(0)[13:], MOCK_LOG_NAME(0))
    watcher.ScanEventLogs()

    log = watcher.GetEventLog(MOCK_LOG_NAME(0))
    self.assertNotEqual(log[event_log_watcher.KEY_OFFSET], 0)


if __name__ == '__main__':
  unittest.main()
