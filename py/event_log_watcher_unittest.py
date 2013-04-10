#!/usr/bin/env python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611

import mox
import os
import shutil
import tempfile
import time
import unittest

from cros.factory import event_log_watcher
from cros.factory.event_log_watcher import EventLogWatcher

MOCK_LOG_NAME = 'mylog12345'
MOCK_PREAMBLE = 'device: 123\nimage: 456\nmd5: abc\n---\n'
MOCK_EVENT = 'seq: 1\nevent: start\n---\n'
MOCK_PERIOD = 0.01

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
    '''Writes text content into a log file.

    If the given log file exists, new content will be appended.

    Args:
      content: the text content to write
      file_name: the name of the log file we're written to
    '''
    file_path = ''
    if file_name is None:
      file_path = tempfile.NamedTemporaryFile(dir=self.events_dir,
          delete=False).name
    else:
      file_path = os.path.join(self.events_dir, file_name)
    with open(file_path, 'a') as f:
      f.write(content)

  def testWatchThread(self):
    class Handler():
      handled = False
      def __init__(self):
        pass
      def handle_cb(self, path, logs):
        self.handled = True
    h = Handler()

    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db,
                              h.handle_cb)
    watcher.StartWatchThread()
    self.WriteLog(MOCK_PREAMBLE)

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

    self.WriteLog(MOCK_PREAMBLE, MOCK_LOG_NAME)

    # Assert nothing stored yet before scan.
    self.assertEqual(watcher.GetEventLog(MOCK_LOG_NAME), None)

    watcher.ScanEventLogs()

    log = watcher.GetEventLog(MOCK_LOG_NAME)
    self.assertNotEqual(log[event_log_watcher.KEY_OFFSET], 0)

    # Write more logs and flush.
    self.WriteLog(MOCK_EVENT, MOCK_LOG_NAME)
    watcher.FlushEventLogs()

    log = watcher.GetEventLog(MOCK_LOG_NAME)
    self.assertEqual(log[event_log_watcher.KEY_OFFSET],
        len(MOCK_PREAMBLE) + len(MOCK_EVENT))

  def testCorruptDb(self):
    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db)

    self.WriteLog(MOCK_PREAMBLE, MOCK_LOG_NAME)

    # Assert nothing stored yet before flush.
    watcher.ScanEventLogs()
    self.assertNotEqual(watcher.GetEventLog(MOCK_LOG_NAME), 0)

    # Manually truncate db file.
    with open(self.db, 'w') as f:
      os.ftruncate(file.fileno(f), 10)

    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db)
    self.assertEqual(watcher.GetEventLog(MOCK_LOG_NAME), None)

  def testHandleEventLogsCallback(self):
    mock = mox.MockAnything()
    mock.handle_event_log(MOCK_LOG_NAME, MOCK_PREAMBLE)
    mox.Replay(mock)

    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db,
                              mock.handle_event_log)

    self.WriteLog(MOCK_PREAMBLE, MOCK_LOG_NAME)
    watcher.ScanEventLogs()

    # Assert that the new log has been marked as handled.
    log = watcher.GetEventLog(MOCK_LOG_NAME)
    self.assertEqual(log[event_log_watcher.KEY_OFFSET],
        len(MOCK_PREAMBLE))

    mox.Verify(mock)

  def testHandleEventLogsFail(self):
    mock = mox.MockAnything()
    mock.handle_event_log(MOCK_LOG_NAME, MOCK_PREAMBLE).AndRaise(
            Exception("Bar"))
    mox.Replay(mock)
    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db,
        mock.handle_event_log)

    self.WriteLog(MOCK_PREAMBLE, MOCK_LOG_NAME)
    watcher.ScanEventLogs()

    # Assert that watcher did not update the new event as uploaded
    # when handle logs fail.
    log = watcher.GetEventLog(MOCK_LOG_NAME)
    self.assertEqual(log[event_log_watcher.KEY_OFFSET], 0)
    mox.Verify(mock)

  def testFlushEventLogsFail(self):
    mock = mox.MockAnything()
    mock.handle_event_log(MOCK_LOG_NAME, MOCK_PREAMBLE).AndRaise(
            Exception("Foo"))
    mox.Replay(mock)
    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db,
        mock.handle_event_log)

    self.WriteLog(MOCK_PREAMBLE, MOCK_LOG_NAME)

    # Assert exception caught.
    self.assertRaises(event_log_watcher.ScanException, watcher.FlushEventLogs)

    # Assert that watcher did not update the new event as uploaded
    # when handle logs fail.
    log = watcher.GetEventLog(MOCK_LOG_NAME)
    self.assertEqual(log[event_log_watcher.KEY_OFFSET], 0)
    mox.Verify(mock)

  def testIncompleteLog(self):
    watcher = EventLogWatcher(MOCK_PERIOD, self.events_dir, self.db)

    # Write the first line of mock preamble as incomplete event log.
    self.WriteLog(MOCK_PREAMBLE[:12] , MOCK_LOG_NAME)
    watcher.ScanEventLogs()

    # Incomplete preamble should be ignored.
    log = watcher.GetEventLog(MOCK_LOG_NAME)
    self.assertEqual(log[event_log_watcher.KEY_OFFSET], 0)

    self.WriteLog(MOCK_PREAMBLE[12:] , MOCK_LOG_NAME)
    watcher.ScanEventLogs()

    log = watcher.GetEventLog(MOCK_LOG_NAME)
    self.assertNotEqual(log[event_log_watcher.KEY_OFFSET], 0)


if __name__ == '__main__':
  unittest.main()
