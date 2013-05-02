#!/usr/bin/python -u
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import mox
import os
import tempfile
import time
import unittest
from urlparse import urlparse

import factory_common  # pylint: disable=W0611
from cros.factory import event_log
from cros.factory.goofy import system_log_manager
from cros.factory.test import shopfloor

MOCK_FILE_PREFIX = 'system_log_manager_unittest'
MOCK_SYNC_LOG_PATHS = [os.path.join('/tmp', MOCK_FILE_PREFIX + '*')]
MOCK_SYNC_PERIOD_SEC = 0.3
MOCK_RSYNC_IO_TIMEOUT = 0
MOCK_SHOPFLOOR_TIMEOUT = 0
MOCK_POLLING_PERIOD = 0.05
MOCK_SERVER_URL = 'http://0.0.0.0:1234'
MOCK_PORT = '8084'
MOCK_DEVICE_ID = 'ab:cd:ef:12:34:56'
MOCK_IMAGE_ID = '123456'
MOCK_RSYNC_DESTINATION = ['rsync://%s:%s/system_logs/%s' %
            (urlparse(MOCK_SERVER_URL).hostname, MOCK_PORT,
             MOCK_DEVICE_ID.replace(':', '') + '_' + MOCK_IMAGE_ID)]
MOCK_RSYNC_COMMAND_ARG = ['rsync', '-azR', '--stats', '--chmod=o-t',
                          '--timeout=%s' % MOCK_RSYNC_IO_TIMEOUT]

class TestSystemLogManager(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()
    self.manager = None
    self.fake_shopfloor = None
    self.fake_process = None
    self._tempfiles = [tempfile.mkstemp(prefix=MOCK_FILE_PREFIX, dir='/tmp')
                       for _ in xrange(3)]
    self.base_rsync_command = (MOCK_RSYNC_COMMAND_ARG +
        sum([glob.glob(x) for x in MOCK_SYNC_LOG_PATHS], []) +
        MOCK_RSYNC_DESTINATION)

  def tearDown(self):
    self.mox.UnsetStubs()
    for x in self._tempfiles:
      os.unlink(x[1])

  def SetMock(self):
    """Sets mocked methods and objects."""
    self.mox.StubOutWithMock(shopfloor, 'get_server_url')
    self.mox.StubOutWithMock(shopfloor, 'get_instance')
    self.mox.StubOutWithMock(event_log, 'GetDeviceId')
    self.mox.StubOutWithMock(event_log, 'GetImageId')
    self.mox.StubOutWithMock(system_log_manager, 'Spawn')
    self.mox.StubOutWithMock(system_log_manager, 'TerminateOrKillProcess')
    self.fake_shopfloor = self.mox.CreateMockAnything()
    self.fake_process = self.mox.CreateMockAnything()

  def AddExtraFilesToRsync(self, extra_files):
    """Inserts extra_files into rsync command before destination part."""
    return (self.base_rsync_command[:-1] + extra_files +
            [self.base_rsync_command[-1]])

  def MockSyncOnce(self, extra_files=None, callback=None,
                   times=3, code=0, terminated=False):
    """Mock rsync once with optional arguments to MockPollToFinish.

    Args:
      extra_files: extra_files argument to from KickSyncThread.
      callback: extra_files argument to from KickSyncThread.
      times: times argument to MockPollToFinish.
      code: times argument to MockPollToFinish.
      terminated: times argument to MockPollToFinish.
    """
    shopfloor.get_server_url().AndReturn(MOCK_SERVER_URL)
    shopfloor.get_instance(detect=True,
        timeout=MOCK_SHOPFLOOR_TIMEOUT).AndReturn(self.fake_shopfloor)
    self.fake_shopfloor.GetFactoryLogPort().AndReturn(MOCK_PORT)
    event_log.GetDeviceId().AndReturn(MOCK_DEVICE_ID)
    event_log.GetImageId().AndReturn(MOCK_IMAGE_ID)
    if extra_files:
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

  def testSyncOnce(self):
    """Syncs onces but and gets a zero returecode."""
    self.SetMock()
    self.MockSyncOnce()

    self.mox.ReplayAll()

    self.manager = system_log_manager.SystemLogManager(
        MOCK_SYNC_LOG_PATHS, MOCK_SYNC_PERIOD_SEC,
        MOCK_SHOPFLOOR_TIMEOUT, MOCK_RSYNC_IO_TIMEOUT,
        MOCK_POLLING_PERIOD)
    self.manager.StartSyncThread()

    #                  poll(N)  poll(N)  poll(N)  poll(Y)
    #                       |        |        |       |
    # -------- ... ------------------------------------------->
    # |                    |                             |
    # start             first sync period              stop

    # MOCK_POLLING_PERIOD * 3.8 is long enough to poll for 4 times.
    time.sleep(MOCK_SYNC_PERIOD_SEC + MOCK_POLLING_PERIOD * 3.8)
    self.manager.StopSyncThread()

    self.mox.VerifyAll()

  def testSyncOnceFail(self):
    """Syncs onces but gets a nonzero returecode."""
    self.SetMock()
    self.MockSyncOnce(code=1)

    self.mox.ReplayAll()

    self.manager = system_log_manager.SystemLogManager(
        MOCK_SYNC_LOG_PATHS, MOCK_SYNC_PERIOD_SEC,
        MOCK_SHOPFLOOR_TIMEOUT, MOCK_RSYNC_IO_TIMEOUT,
        MOCK_POLLING_PERIOD)
    self.manager.StartSyncThread()
    time.sleep(MOCK_SYNC_PERIOD_SEC + MOCK_POLLING_PERIOD * 3.8)
    self.manager.StopSyncThread()

    self.mox.VerifyAll()

  def testSyncOnceTerminated(self):
    """Syncs once but rsync takes too long and gets terminated."""
    self.SetMock()
    self.MockSyncOnce(times=2, terminated=True)

    # Setting polling period to 2/3 of sync period, and let poll
    # returns None for 2 times. There will be two polls before it aborts.
    # See the time diagram below.
    #
    #               poll(N)  poll(N)  aborted before the 3rd poll
    #               |        |        x
    #---------------------------------------------->
    #|             |             |             |
    #          1 period      2 period
    #start       _SyncLogs()                  stop

    self.mox.ReplayAll()

    mock_polling_period = MOCK_SYNC_PERIOD_SEC * 2 / 3
    self.manager = system_log_manager.SystemLogManager(
        MOCK_SYNC_LOG_PATHS, MOCK_SYNC_PERIOD_SEC,
        MOCK_SHOPFLOOR_TIMEOUT, MOCK_RSYNC_IO_TIMEOUT,
        mock_polling_period)
    self.manager.StartSyncThread()
    time.sleep(MOCK_SYNC_PERIOD_SEC + mock_polling_period * 3)
    self.manager.StopSyncThread()

    self.mox.VerifyAll()

  def testSyncPeriodic(self):
    """Syncs periodically for 5 times."""
    self.SetMock()
    number_of_period = 5
    for _ in xrange(number_of_period):
      self.MockSyncOnce()

    self.mox.ReplayAll()

    self.manager = system_log_manager.SystemLogManager(
        MOCK_SYNC_LOG_PATHS, MOCK_SYNC_PERIOD_SEC,
        MOCK_SHOPFLOOR_TIMEOUT, MOCK_RSYNC_IO_TIMEOUT,
        MOCK_POLLING_PERIOD)
    self.manager.StartSyncThread()
    time.sleep((MOCK_SYNC_PERIOD_SEC + MOCK_POLLING_PERIOD * 3.8) *
               number_of_period)
    self.manager.StopSyncThread()

    self.mox.VerifyAll()

  def testSyncKickNoPeriodic(self):
    """Syncs by a kick without periodic sync"""
    self.SetMock()

    mock_extra_files = ['mock_extra_files']
    mock_callback = self.mox.CreateMockAnything()
    self.MockSyncOnce(mock_extra_files, mock_callback)

    self.mox.ReplayAll()

    self.manager = system_log_manager.SystemLogManager(
        MOCK_SYNC_LOG_PATHS, None,
        MOCK_SHOPFLOOR_TIMEOUT, MOCK_RSYNC_IO_TIMEOUT,
        MOCK_POLLING_PERIOD)
    self.manager.StartSyncThread()
    # manager should only sync once, which is kicked by the test.
    self.manager.KickSyncThread(mock_extra_files, mock_callback)
    time.sleep(MOCK_POLLING_PERIOD * 3.8)
    self.manager.StopSyncThread()

    self.mox.VerifyAll()

  def testSyncKick(self):
    """Syncs by a kick before the first periodic sync occurs."""
    self.SetMock()

    mock_extra_files = ['mock_extra_files']
    mock_callback = self.mox.CreateMockAnything()
    self.MockSyncOnce(mock_extra_files, mock_callback)

    self.mox.ReplayAll()

    self.manager = system_log_manager.SystemLogManager(
        MOCK_SYNC_LOG_PATHS, MOCK_SYNC_PERIOD_SEC,
        MOCK_SHOPFLOOR_TIMEOUT, MOCK_RSYNC_IO_TIMEOUT,
        MOCK_POLLING_PERIOD)
    self.manager.StartSyncThread()
    # manager should only sync once, which is kicked by the test.
    self.manager.KickSyncThread(mock_extra_files, mock_callback)
    time.sleep(MOCK_POLLING_PERIOD * 3.8)
    self.manager.StopSyncThread()

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

    self.mox.ReplayAll()

    self.manager = system_log_manager.SystemLogManager(
        MOCK_SYNC_LOG_PATHS, MOCK_SYNC_PERIOD_SEC,
        MOCK_SHOPFLOOR_TIMEOUT, MOCK_RSYNC_IO_TIMEOUT,
        MOCK_POLLING_PERIOD)
    self.manager.StartSyncThread()
    # manager should sync twice in this time
    time.sleep((MOCK_SYNC_PERIOD_SEC + MOCK_POLLING_PERIOD * 3.8) * 2)
    # manager is kiced by the test to sync once.
    self.manager.KickSyncThread(mock_extra_files, mock_callback)
    time.sleep(MOCK_POLLING_PERIOD * 3.8)
    # manager should sync twice in this time
    time.sleep((MOCK_SYNC_PERIOD_SEC + MOCK_POLLING_PERIOD * 3.8) * 2)
    self.manager.StopSyncThread()

    self.mox.VerifyAll()

  def testSyncPeriodAndKickToTerminate(self):
    """Gets kicked during periodic sync, then terminate periodic sync."""
    self.SetMock()
    # This sync will get terminated by kick event.
    self.MockSyncOnce(terminated=True)

    mock_extra_files = ['mock_extra_files']
    mock_callback = self.mox.CreateMockAnything()
    self.MockSyncOnce(mock_extra_files, mock_callback)

    number_of_period_after_kick = 2
    for _ in xrange(number_of_period_after_kick):
      self.MockSyncOnce()

    self.mox.ReplayAll()

    self.manager = system_log_manager.SystemLogManager(
        MOCK_SYNC_LOG_PATHS, MOCK_SYNC_PERIOD_SEC,
        MOCK_SHOPFLOOR_TIMEOUT, MOCK_RSYNC_IO_TIMEOUT,
        MOCK_POLLING_PERIOD)
    self.manager.StartSyncThread()
    # manager should fire a sync after this time.
    time.sleep(MOCK_SYNC_PERIOD_SEC * 1)
    # manager thread should poll three times.
    time.sleep(MOCK_POLLING_PERIOD * 2.8)
    # manager is kiced by the test to terminate previous sync and
    # starts a new sync.
    self.manager.KickSyncThread(mock_extra_files, mock_callback)
    # manager thread should poll four times to succeed.
    time.sleep(MOCK_POLLING_PERIOD * 3.8)

    # manager should sync periodically for two times in this time
    # after the sync of kick.
    time.sleep((MOCK_SYNC_PERIOD_SEC + MOCK_POLLING_PERIOD * 3.8) * 2)
    self.manager.StopSyncThread()

    self.mox.VerifyAll()


if __name__ == "__main__":
  unittest.main()
