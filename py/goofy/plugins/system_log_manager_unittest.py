#!/usr/bin/env python2
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for system_log_manager.py."""


import glob
import logging
import os
import Queue
import shutil
import threading
import unittest
from urlparse import urlparse

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.test import server_proxy
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.utils import debug_utils
from cros.factory.utils import file_utils

# Mocks CatchException decorator since it will suppress exception in
# SystemLogManager.
CatchExceptionImpl = debug_utils.CatchException


def CatchExceptionDisabled(*args, **kwargs):
  kwargs['enable'] = False
  return CatchExceptionImpl(*args, **kwargs)
debug_utils.CatchException = CatchExceptionDisabled

# pylint: disable=wrong-import-position
from cros.factory.goofy.plugins import system_log_manager
# pylint: enable=wrong-import-position

TEST_DIRECTORY = '/tmp/system_log_manager_unittest_%s_/' % os.getpid()
mock_file_prefix = 'system_log_manager_unittest_%s_' % os.getpid()
mock_sync_log_paths = [os.path.join(TEST_DIRECTORY, mock_file_prefix + '*')]

MOCK_SYNC_PERIOD_SEC = 0.6
MOCK_MIN_SYNC_PERIOD_SEC = 0.5
MOCK_SCAN_PERIOD_SEC = 0.2
MOCK_RSYNC_IO_TIMEOUT = 0
MOCK_POLLING_PERIOD = 0.05
MOCK_POLLING_FAIL_TRIES = 3
MOCK_POLLING_DURATION = 3.8 * MOCK_POLLING_PERIOD
# MOCK_POLLING_PERIOD * 3.8 is long enough to poll for 4 times.
#
#        poll(N)  poll(N)  poll(N)  poll(Y)
#          |        |        |       |
# ---------------------------------------------->
# |      |                             |
# start first sync                    stop

MOCK_SERVER_URL = 'http://0.0.0.0:1234'
MOCK_PORT = '8084'
MOCK_DEVICE_ID = 'abcdef0123456789abcdef0123456789'
MOCK_RSYNC_DESTINATION = [
    'rsync://%s:%s/system_logs/%s' %
    (urlparse(MOCK_SERVER_URL).hostname, MOCK_PORT, MOCK_DEVICE_ID)]
MOCK_RSYNC_COMMAND_ARG = ['rsync', '-azR', '--stats', '--chmod=o-t',
                          '--timeout=%s' % MOCK_RSYNC_IO_TIMEOUT]


def CreateTestFile(prefix):
  return file_utils.CreateTemporaryFile(prefix=prefix, dir=TEST_DIRECTORY)


# TODO(pihsun): Refactor this file to use mock_time_utils.


class StubTimer(object):
  def __init__(self):
    self.fake_time = 0

  def __str__(self):
    return '(t=%s)' % self.fake_time

  def time(self):
    return self.fake_time

class StubQueue(object):
  def __init__(self, timer, items, assert_func):
    self.get_index = 0
    self.put_index = 0
    self.timer = timer
    self.items = items
    self.assert_func = assert_func

  def get(self, block, timeout):
    logging.debug('%s StubQueue.get(%s, %s), get_index = %d',
                  self.timer, block, timeout, self.get_index)
    if self.get_index < len(self.items):
      item_put_time, item = self.items[self.get_index]
      if item_put_time <= self.timer.fake_time + timeout:
        self.get_index += 1
        self.timer.fake_time = item_put_time
        return item
    self.timer.fake_time += timeout
    raise Queue.Empty

  def put(self, item):
    logging.debug('%s StubQueue.put(%r), put_index = %d',
                  self.timer, item, self.put_index)
    self.assert_func(self.put_index < len(self.items))
    self.assert_func(item == self.items[self.put_index][1])
    self.put_index += 1

  def task_done(self):
    logging.debug('%s StubQueue.task_done()', self.timer)

class StubAbortEvent(object):
  def __init__(self, timer, abort_time, notify_event=None):
    self.timer = timer
    self.abort_time = abort_time
    self.notify_event = notify_event

  def set(self):
    logging.debug('%s StubAbortEvent.set()', self.timer)

  def wait(self, t):
    logging.debug('%s StubAbortEvent.wait(%s)', self.timer, t)
    if self.timer.fake_time + t >= self.abort_time:
      self.timer.fake_time = self.abort_time
    else:
      self.timer.fake_time += t

  def isSet(self):
    logging.debug('%s StubAbortEvent.isSet()', self.timer)
    if self.timer.fake_time >= self.abort_time:
      # We're going to abort, wait notify_event if there's any, to avoid that
      # we abort before remaining of unittest is done, causing race condition.
      if self.notify_event:
        self.notify_event.wait()
      return True
    else:
      return False

class TestSystemLogManager(unittest.TestCase):
  """Unittest for SystemLogManager."""

  def setUp(self):
    self.mox = mox.Mox()
    self.goofy = None
    self.manager = None
    self.fake_server_proxy = None
    self.fake_process = None
    self.abort_time = None
    self.requests = []
    self.kicks = []
    self.kick_replayed_event = threading.Event()
    file_utils.TryMakeDirs(TEST_DIRECTORY)
    self.ClearFiles()
    self._tempfiles = [CreateTestFile(mock_file_prefix)
                       for unused_index in xrange(3)]
    self.base_rsync_command = (
        MOCK_RSYNC_COMMAND_ARG +
        sum([glob.glob(x) for x in mock_sync_log_paths], []) +
        MOCK_RSYNC_DESTINATION)
    # Modifies the minimum sync log period secs in system_log_manager for
    # unittest.
    system_log_manager.MIN_SYNC_LOG_PERIOD_SECS = MOCK_MIN_SYNC_PERIOD_SEC

  def ClearFiles(self):
    clear_files = glob.glob(
        os.path.join(TEST_DIRECTORY, mock_file_prefix + '*'))
    logging.debug('Clearing %r', clear_files)
    for x in clear_files:
      file_utils.TryUnlink(x)

  def tearDown(self):
    logging.debug('tearDown')
    try:
      self.manager.OnStop()
    except Exception:
      pass
    self.mox.UnsetStubs()
    self.ClearFiles()
    shutil.rmtree(TEST_DIRECTORY)

  def SetMock(self):
    """Sets mocked methods and objects."""
    self.mox.StubOutWithMock(server_proxy, 'GetServerURL')
    self.mox.StubOutWithMock(server_proxy, 'GetServerProxy')
    self.mox.StubOutWithMock(session, 'GetDeviceID')
    self.mox.StubOutWithMock(system_log_manager, 'Spawn')
    self.mox.StubOutWithMock(system_log_manager, 'TerminateOrKillProcess')
    self.fake_server_proxy = self.mox.CreateMockAnything()
    self.fake_process = self.mox.CreateMockAnything()
    self.goofy = self.mox.CreateMockAnything()
    self.goofy.state_instance = state.StubFactoryState()

  def AddExtraFilesToRsync(self, extra_files):
    """Inserts extra_files into rsync command before destination part."""
    return (self.base_rsync_command[:-1] + extra_files +
            [self.base_rsync_command[-1]])

  def MockStopAt(self, abort_time):
    self.abort_time = abort_time
    # An extra request is generated at OnStop()
    self.requests.append((self.abort_time,
                          system_log_manager.KickRequest([], None, False)))

  def MockSyncOnce(self, extra_files=None, callback=None,
                   times=MOCK_POLLING_FAIL_TRIES, code=0, terminated=False):
    """Mock rsync once with optional arguments to MockPollToFinish.

    Args:
      extra_files: extra_files argument to KickToSync.
      callback: extra_files argument to KickToSync.
      times: times argument to MockPollToFinish.
      code: code argument to MockPollToFinish.
      terminated: terminated argument to MockPollToFinish.
    """
    server_proxy.GetServerURL().AndReturn(MOCK_SERVER_URL)
    server_proxy.GetServerProxy().AndReturn(self.fake_server_proxy)
    self.fake_server_proxy.GetFactoryLogPort().AndReturn(MOCK_PORT)
    session.GetDeviceID().AndReturn(MOCK_DEVICE_ID)
    if extra_files:
      logging.debug('Mocks getting extra_files %r', extra_files)
      mock_rsync_command = self.AddExtraFilesToRsync(extra_files)
    else:
      mock_rsync_command = self.base_rsync_command
    system_log_manager.Spawn(mock_rsync_command, ignore_stdout=True,
                             ignore_stderr=True).AndReturn(self.fake_process)

    self.MockPollToFinish(times=times, code=code, terminated=terminated)
    if not self.fake_process.returncode and callback:
      callback(extra_files)

  def MockPollToFinish(self, times=3, code=0, terminated=False):
    """Mocks that rsync takes times polls before finish or gets terminated.

    Args:
      times: Number of polling which gets None (busy). This number does not
          include the last polling which gets True (If not getting terminated).
      code: Return code of rsync subprocess.
      terminated: Rsync subprocess gets terminated after times pollings.
    """
    for _ in xrange(times):
      self.fake_process.poll().AndReturn(None)
    if terminated:
      system_log_manager.TerminateOrKillProcess(self.fake_process)
      return
    self.fake_process.poll().AndReturn(True)
    self.fake_process.returncode = code

  def GetSystemLogManagerWithStub(self, *args, **kwargs):
    """Set self.manager to a new SystemLogManager, with some attributes stubbed
    for testing.

    This should be called after all self.Mock*, self.RecordKickTo* are called.
    """
    self.manager = system_log_manager.SystemLogManager(*args, **kwargs)
    timer = StubTimer()
    # pylint: disable=protected-access
    self.manager._timer = timer.time
    self.manager._queue = StubQueue(timer, self.requests, self.assertTrue)
    self.manager._aborted = StubAbortEvent(
        timer, self.abort_time,
        self.kick_replayed_event if self.kicks else None)

  def RecordKickToSync(self, extra_files=None, callback=None, time_at=0):
    self.kicks.append(('KickToSync', [extra_files, callback]))
    self.requests.append(
        (time_at, system_log_manager.KickRequest(extra_files, callback, False)))

  def RecordKickToClear(self, time_at=0):
    self.kicks.append(('KickToClear', []))
    self.requests.append(
        (time_at, system_log_manager.KickRequest([], None, True)))

  def ReplayKicks(self):
    for func, args in self.kicks:
      getattr(self.manager, func)(*args)
    self.kick_replayed_event.set()

  def testSyncOnce(self):
    """Syncs onces and gets a zero returecode."""
    self.SetMock()
    self.MockSyncOnce()
    self.MockStopAt(MOCK_SCAN_PERIOD_SEC + MOCK_POLLING_DURATION)

    self.mox.ReplayAll()

    self.GetSystemLogManagerWithStub(
        self.goofy, mock_sync_log_paths, MOCK_SYNC_PERIOD_SEC,
        MOCK_SCAN_PERIOD_SEC, MOCK_RSYNC_IO_TIMEOUT,
        MOCK_POLLING_PERIOD)
    self.manager.Start()
    self.manager.Stop()

    self.mox.VerifyAll()

  def testSyncOnceFail(self):
    """Syncs onces but gets a nonzero returecode."""
    self.SetMock()
    self.MockSyncOnce(code=1)
    self.MockStopAt(MOCK_SCAN_PERIOD_SEC + MOCK_POLLING_DURATION)

    self.mox.ReplayAll()

    self.GetSystemLogManagerWithStub(
        self.goofy, mock_sync_log_paths, MOCK_SYNC_PERIOD_SEC,
        MOCK_SCAN_PERIOD_SEC, MOCK_RSYNC_IO_TIMEOUT,
        MOCK_POLLING_PERIOD)
    self.manager.Start()
    self.manager.Stop()

    self.mox.VerifyAll()

  def testSyncOnceStopped(self):
    """Syncs once but rsync takes too long and manager got stopped."""
    self.SetMock()
    self.MockSyncOnce(times=2, terminated=True)

    # Setting polling period to 1/5 of scan period, and let poll
    # returns None for 2 times. There will be two polls before it aborts by
    # Stop().
    # See the time diagram below.
    #
    #       poll(N)    poll(N)   aborted before the 3rd poll
    #       |          |         x
    #--...--------------------------------------------->
    #|      |                    |
    #      1st
    # start _SyncLogs()         stop

    mock_polling_period = MOCK_SCAN_PERIOD_SEC * 1 / 5
    self.MockStopAt(MOCK_SCAN_PERIOD_SEC + mock_polling_period * 2)

    self.mox.ReplayAll()

    self.GetSystemLogManagerWithStub(
        self.goofy, mock_sync_log_paths, MOCK_SYNC_PERIOD_SEC,
        MOCK_SCAN_PERIOD_SEC, MOCK_RSYNC_IO_TIMEOUT,
        mock_polling_period)
    self.manager.Start()
    self.manager.Stop()

    self.mox.VerifyAll()

  def testSyncOnceTerminated(self):
    """Syncs once but rsync takes too long and gets terminated."""
    self.SetMock()
    self.MockSyncOnce(times=2, terminated=True)

    # Setting polling period to 2/3 of scan period, and let poll
    # returns None for 2 times. There will be two polls before it aborts.
    # See the time diagram below.
    #
    #               poll(N)  poll(N)  aborted before the 3rd poll
    #               |        |        x
    #---------------------------------------------->
    #|             |             |             |
    #             1st scan     2nd scan
    # start       _SyncLogs()                  stop

    mock_polling_period = MOCK_SCAN_PERIOD_SEC * 2 / 3
    self.MockStopAt(MOCK_SCAN_PERIOD_SEC + mock_polling_period * 3)

    self.mox.ReplayAll()

    self.GetSystemLogManagerWithStub(
        self.goofy, mock_sync_log_paths, MOCK_SYNC_PERIOD_SEC,
        MOCK_SCAN_PERIOD_SEC, MOCK_RSYNC_IO_TIMEOUT,
        mock_polling_period)
    self.manager.Start()
    self.manager.Stop()

    self.mox.VerifyAll()

  def testSyncPeriodic(self):
    """Syncs periodically for 5 times."""
    self.SetMock()
    number_of_period = 5
    for _ in xrange(number_of_period):
      self.MockSyncOnce()
    self.MockStopAt(MOCK_SCAN_PERIOD_SEC +
                    ((MOCK_SYNC_PERIOD_SEC + MOCK_POLLING_DURATION) *
                     (number_of_period - 1)) + MOCK_POLLING_DURATION)

    self.mox.ReplayAll()

    self.GetSystemLogManagerWithStub(
        self.goofy, mock_sync_log_paths, MOCK_SYNC_PERIOD_SEC,
        MOCK_SCAN_PERIOD_SEC, MOCK_RSYNC_IO_TIMEOUT,
        MOCK_POLLING_PERIOD)
    self.manager.Start()
    self.manager.Stop()

    self.mox.VerifyAll()

  def testSyncKickNoPeriodic(self):
    """Syncs by a kick without periodic sync"""
    self.SetMock()

    mock_extra_files = ['mock_extra_files']
    mock_callback = self.mox.CreateMockAnything()

    self.MockSyncOnce(mock_extra_files, mock_callback)
    # manager should only sync once, which is kicked by the test.
    self.RecordKickToSync(mock_extra_files, mock_callback)
    self.MockStopAt(MOCK_POLLING_DURATION)

    self.mox.ReplayAll()

    self.GetSystemLogManagerWithStub(
        self.goofy, mock_sync_log_paths, None, MOCK_SCAN_PERIOD_SEC,
        MOCK_RSYNC_IO_TIMEOUT, MOCK_POLLING_PERIOD, [])
    self.manager.Start()
    self.ReplayKicks()
    self.manager.Stop()

    self.mox.VerifyAll()

  def testSyncKick(self):
    """Syncs by a kick before the first periodic sync occurs."""
    self.SetMock()

    mock_extra_files = ['mock_extra_files']
    mock_callback = self.mox.CreateMockAnything()
    self.MockSyncOnce(mock_extra_files, mock_callback)
    # manager should only sync once, which is kicked by the test.
    self.RecordKickToSync(mock_extra_files, mock_callback)
    self.MockStopAt(MOCK_POLLING_DURATION)

    self.mox.ReplayAll()

    self.GetSystemLogManagerWithStub(
        self.goofy, mock_sync_log_paths, MOCK_SYNC_PERIOD_SEC,
        MOCK_SCAN_PERIOD_SEC, MOCK_RSYNC_IO_TIMEOUT, MOCK_POLLING_PERIOD)
    self.manager.Start()
    self.ReplayKicks()
    self.manager.Stop()

    self.mox.VerifyAll()

  def testSyncKickMultipleTimes(self):
    """Syncs by multiple kicks."""
    self.SetMock()

    times = 5
    mock_extra_files = [['mock_extra_files_%d' % x] for x in xrange(times)]
    mock_callback = self.mox.CreateMockAnything()

    for kick_number in xrange(times):
      self.MockSyncOnce(mock_extra_files[kick_number], mock_callback)
    # manager should process each sync requests by the test.
    for kick_number in xrange(times):
      self.RecordKickToSync(
          mock_extra_files[kick_number], mock_callback)
    self.MockStopAt(MOCK_POLLING_DURATION * times)

    self.mox.ReplayAll()

    self.GetSystemLogManagerWithStub(
        self.goofy, mock_sync_log_paths, None, MOCK_SCAN_PERIOD_SEC,
        MOCK_RSYNC_IO_TIMEOUT, MOCK_POLLING_PERIOD, [])
    self.manager.Start()
    self.ReplayKicks()
    self.manager.Stop()

    self.mox.VerifyAll()

  def testSyncPeriodAndKick(self):
    """Syncs periodically for two times and gets kicked.

    After the sync of kick succeeds, sync for another two times periodically.
    """
    self.SetMock()
    number_of_period_before_kick = 2
    for _ in xrange(number_of_period_before_kick):
      self.MockSyncOnce()

    mock_extra_files = ['mock_extra_files']
    mock_callback = self.mox.CreateMockAnything()
    self.MockSyncOnce(mock_extra_files, mock_callback)

    number_of_period_after_kick = 2
    for _ in xrange(number_of_period_after_kick):
      self.MockSyncOnce()

    # manager should sync twice in this time
    t = (MOCK_SCAN_PERIOD_SEC + MOCK_POLLING_DURATION +
         MOCK_SYNC_PERIOD_SEC + MOCK_POLLING_DURATION)
    # manager is kiced by the test to sync once.
    self.RecordKickToSync(mock_extra_files, mock_callback, time_at=t)
    t += MOCK_POLLING_DURATION
    # manager should sync twice in this time
    t += (MOCK_SYNC_PERIOD_SEC + MOCK_POLLING_DURATION +
          MOCK_SYNC_PERIOD_SEC + MOCK_POLLING_DURATION)
    self.MockStopAt(t)

    self.mox.ReplayAll()

    self.GetSystemLogManagerWithStub(
        self.goofy, mock_sync_log_paths, MOCK_SYNC_PERIOD_SEC,
        MOCK_SCAN_PERIOD_SEC, MOCK_RSYNC_IO_TIMEOUT, MOCK_POLLING_PERIOD)
    self.manager.Start()
    self.ReplayKicks()
    self.manager.Stop()

    self.mox.VerifyAll()

  def testSyncPeriodAndKickToSync(self):
    """Gets kicked during periodic sync, then it put request to queue."""
    self.SetMock()
    # This sync will get terminated by kick event.
    self.MockSyncOnce()

    mock_extra_files = ['mock_extra_files']
    mock_callback = self.mox.CreateMockAnything()
    self.MockSyncOnce(mock_extra_files, mock_callback)

    number_of_period_after_kick = 2
    for _ in xrange(number_of_period_after_kick):
      self.MockSyncOnce()

    # manager should fire a sync after this time.
    t = MOCK_SCAN_PERIOD_SEC * 1
    # manager thread should poll MOCK_POLLING_FAIL_TRIES times.
    t += MOCK_POLLING_PERIOD * MOCK_POLLING_FAIL_TRIES
    # manager is kiced by the test and put a request to queue.
    self.RecordKickToSync(mock_extra_files, mock_callback, time_at=t)
    # manager thread should poll onces and finish the first sync.
    t += MOCK_POLLING_PERIOD
    # manager then does the sync request in the queue.
    t += MOCK_POLLING_DURATION

    # manager should sync periodically for two times in this time
    # after the sync of kick.
    t += (MOCK_SYNC_PERIOD_SEC + MOCK_POLLING_DURATION) * 2
    self.MockStopAt(t)

    self.mox.ReplayAll()

    self.GetSystemLogManagerWithStub(
        self.goofy, mock_sync_log_paths, MOCK_SYNC_PERIOD_SEC,
        MOCK_SCAN_PERIOD_SEC, MOCK_RSYNC_IO_TIMEOUT, MOCK_POLLING_PERIOD)
    self.manager.Start()
    self.ReplayKicks()
    self.manager.Stop()

    self.mox.VerifyAll()

  def testClearOnce(self):
    """Clears log files once by periodic scan including syncing."""
    self.SetMock()
    clear_file_prefix = mock_file_prefix + 'clear_'
    for _ in xrange(3):
      CreateTestFile(clear_file_prefix)
    clear_file_paths = [os.path.join(TEST_DIRECTORY, clear_file_prefix + '*')]
    self.MockSyncOnce()
    self.MockStopAt((MOCK_SCAN_PERIOD_SEC + MOCK_POLLING_DURATION) * 2)

    self.mox.ReplayAll()

    self.GetSystemLogManagerWithStub(
        self.goofy, mock_sync_log_paths, MOCK_SYNC_PERIOD_SEC,
        MOCK_SCAN_PERIOD_SEC, MOCK_RSYNC_IO_TIMEOUT, MOCK_POLLING_PERIOD,
        clear_file_paths)
    self.manager.Start()
    self.manager.Stop()

    self.mox.VerifyAll()
    self.assertEqual(sum([glob.glob(x) for x in clear_file_paths], []), [])

  def testClearOnceWithoutSync(self):
    """Clears log files once by periodic scan without syncing."""
    self.SetMock()
    clear_file_prefix = mock_file_prefix + 'clear_'
    for _ in xrange(3):
      CreateTestFile(clear_file_prefix)
    clear_file_paths = [os.path.join(TEST_DIRECTORY, clear_file_prefix + '*')]

    self.MockStopAt(MOCK_SCAN_PERIOD_SEC)

    self.mox.ReplayAll()

    self.GetSystemLogManagerWithStub(
        self.goofy, mock_sync_log_paths, None, MOCK_SCAN_PERIOD_SEC,
        MOCK_RSYNC_IO_TIMEOUT, MOCK_POLLING_PERIOD, clear_file_paths)
    self.manager.Start()
    self.manager.Stop()

    self.mox.VerifyAll()
    self.assertEqual(sum([glob.glob(x) for x in clear_file_paths], []), [])

  def testClearOnceByKickWithoutSync(self):
    """Clears log files once by KickToClear without syncing."""
    self.SetMock()
    clear_file_prefix = mock_file_prefix + 'clear_'
    for _ in xrange(3):
      CreateTestFile(clear_file_prefix)
    clear_file_paths = [os.path.join(TEST_DIRECTORY, clear_file_prefix + '*')]

    self.RecordKickToClear()
    self.MockStopAt(0)

    self.mox.ReplayAll()

    self.GetSystemLogManagerWithStub(
        self.goofy, mock_sync_log_paths, None, MOCK_SCAN_PERIOD_SEC,
        MOCK_RSYNC_IO_TIMEOUT, MOCK_POLLING_PERIOD, clear_file_paths)
    self.manager.Start()
    self.ReplayKicks()
    self.manager.Stop()

    self.mox.VerifyAll()
    self.assertEqual(sum([glob.glob(x) for x in clear_file_paths], []), [])

  def testClearOnceExclusiveByKickWithoutSync(self):
    """Clears log files once by KickToClear without syncing."""
    self.SetMock()
    clear_file_prefix = mock_file_prefix + 'clear_'
    for _ in xrange(3):
      CreateTestFile(clear_file_prefix)
    preserve_file_prefix = clear_file_prefix + 'preserve_'
    for _ in xrange(3):
      CreateTestFile(preserve_file_prefix)
    clear_file_paths = [os.path.join(TEST_DIRECTORY, clear_file_prefix + '*')]
    clear_file_excluded_paths = [
        os.path.join(TEST_DIRECTORY, preserve_file_prefix + '*')]

    self.RecordKickToClear()
    self.MockStopAt(0)

    self.mox.ReplayAll()

    self.GetSystemLogManagerWithStub(
        self.goofy, mock_sync_log_paths, None, MOCK_SCAN_PERIOD_SEC,
        MOCK_RSYNC_IO_TIMEOUT, MOCK_POLLING_PERIOD, clear_file_paths,
        clear_file_excluded_paths)
    self.manager.Start()
    self.ReplayKicks()
    self.manager.Stop()

    self.mox.VerifyAll()
    self.assertEqual(
        sum([glob.glob(os.path.join(TEST_DIRECTORY,
                                    clear_file_prefix + '*'))],
            []),
        sum([glob.glob(os.path.join(TEST_DIRECTORY,
                                    preserve_file_prefix + '*'))],
            []))
    self.assertEqual(len(sum([glob.glob(
        os.path.join(TEST_DIRECTORY, preserve_file_prefix + '*'))], [])), 3)

  def testCheckSetting(self):
    """Unittest for _CheckSettings method."""
    self.SetMock()

    # sync_log_period_secs is less than MIN_SYNC_LOG_PERIOD_SECS.
    with self.assertRaises(system_log_manager.SystemLogManagerException):
      self.GetSystemLogManagerWithStub(
          self.goofy, mock_sync_log_paths, 0.5 * MOCK_MIN_SYNC_PERIOD_SEC,
          MOCK_SCAN_PERIOD_SEC, MOCK_RSYNC_IO_TIMEOUT, MOCK_POLLING_PERIOD, [])

    # scan_log_period_secs is greater than sync_log_period_secs.
    with self.assertRaises(system_log_manager.SystemLogManagerException):
      self.GetSystemLogManagerWithStub(
          self.goofy, mock_sync_log_paths, MOCK_SYNC_PERIOD_SEC,
          1.5 * MOCK_SYNC_PERIOD_SEC, MOCK_RSYNC_IO_TIMEOUT,
          MOCK_POLLING_PERIOD, [])

    # clear_log_paths should be a list.
    with self.assertRaises(system_log_manager.SystemLogManagerException):
      self.GetSystemLogManagerWithStub(
          self.goofy, ['/foo/bar1', '/foo/bar2'], MOCK_SYNC_PERIOD_SEC,
          MOCK_SCAN_PERIOD_SEC, MOCK_RSYNC_IO_TIMEOUT, MOCK_POLLING_PERIOD,
          '/foo/bar1')

    # clear_log_excluded_paths should be a list.
    with self.assertRaises(system_log_manager.SystemLogManagerException):
      self.GetSystemLogManagerWithStub(
          self.goofy, ['/foo/bar1', '/foo/bar2'], MOCK_SYNC_PERIOD_SEC,
          MOCK_SCAN_PERIOD_SEC, MOCK_RSYNC_IO_TIMEOUT, MOCK_POLLING_PERIOD,
          ['/foo/bar3'], '/foo/bar4')

    # clear_log_paths and sync_log_paths have paths in common.
    with self.assertRaises(system_log_manager.SystemLogManagerException):
      self.GetSystemLogManagerWithStub(
          self.goofy, ['/foo/bar1', '/foo/bar2'], MOCK_SYNC_PERIOD_SEC,
          MOCK_SCAN_PERIOD_SEC, MOCK_RSYNC_IO_TIMEOUT, MOCK_POLLING_PERIOD,
          ['/foo/bar1', '/foo/bar3'])

    # clear_log_paths and clear_log_excluded_paths have paths in common.
    with self.assertRaises(system_log_manager.SystemLogManagerException):
      self.GetSystemLogManagerWithStub(
          self.goofy, ['/foo/bar1', '/foo/bar2'], MOCK_SYNC_PERIOD_SEC,
          MOCK_SCAN_PERIOD_SEC, MOCK_RSYNC_IO_TIMEOUT, MOCK_POLLING_PERIOD,
          ['/foo/bar1', '/foo/bar2'], ['/foo/bar1', '/foo/bar3'])


if __name__ == '__main__':
  logging.basicConfig(format='%(asctime)s:%(levelname)s:%(message)s',
                      level=logging.DEBUG)
  unittest.main()
