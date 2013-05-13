# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import os
import sys
import threading
import time
import traceback
from urlparse import urlparse

import factory_common  # pylint: disable=W0611
from cros.factory import event_log
from cros.factory.test import shopfloor
from cros.factory.utils.process_utils import Spawn, TerminateOrKillProcess


class SystemLogManagerException(Exception):
  pass


class SystemLogManager(object):
  """The manager that takes care of system log files.

  Properties:
    clear_log_paths: A list of log paths to clear.
    sync_log_paths: A list of log paths to sync.
    sync_period_sec: The time period in seconds between consecutive syncs.
      If set to None, manager will only sync upon being kicked.
    shopfloor_timeout: Timeout to get shopfloor instance.
    rsync_io_timeout: I/O timeout argument in rsync command.
    sync_thread: The thread to sync logs periodically.
    aborted: The event to abort sync_thread.
    kick: The event to kick sync_thread to sync logs.
    extra_files: A list of extra files to sync.
    callback: A callback to call after sync succeeds. extra_files will be the
        argument of callback. This is to serve the case such as delete the
        files after syncing them to server.
    polling_period: The period to poll rsync subprocess.
  """
  def __init__(self, sync_log_paths, sync_period_sec=300, shopfloor_timeout=5,
               rsync_io_timeout=5, polling_period=1, clear_log_paths=None):
    self._sync_log_paths = sync_log_paths
    self._sync_period_sec = sync_period_sec
    self._shopfloor_timeout = shopfloor_timeout
    self._rsync_io_timeout = rsync_io_timeout
    self._sync_thread = None
    self._aborted = threading.Event()
    self._kick = threading.Event()
    self._extra_files = []
    self._callback = None
    self._polling_period = polling_period
    self._clear_log_paths = clear_log_paths if clear_log_paths else []

  def IsThreadRunning(self):
    """Returns True if _sync_thread is running."""
    return self._sync_thread and self._sync_thread.isAlive()

  def KickSyncThread(self, extra_files=None, callback=None):
    """Kicks _sync_thread to sync logs with extra files and a callbalk.

    Accpets only one kick before it is processed. If _kick is set, it means
    the last kick event is still processing. By processing it means to pass
    extra_files, callback into _sync_thread, and ready to do a sync.

    Args:
      extra_files: A list of extra files to sync.
      callback: A callback to call after sync succeeds.

    Returns:
      If kick has been set by another call and is not processed yet,
      return False, else return True.

    Raises:
      SystemLogManagerException: If thread is not running.
    """
    if not self.IsThreadRunning():
      raise SystemLogManagerException('Thread is not running.')
    if self._kick.isSet():
      return False
    if extra_files is None:
      extra_files = []
    self._extra_files = extra_files
    self._callback = callback
    self._kick.set()
    return True

  def StartSyncThread(self):
    """Starts _sync_thread."""
    logging.info('Start sync thread.')
    self._sync_thread = threading.Thread(target=self._RunForever,
                                         name='SystemLogManager')
    self._sync_thread.start()

  def StopSyncThread(self):
    """Stops _sync_thread.

    Raises:
      SystemLogManagerException: If thread is not running.
    """
    if not self.IsThreadRunning():
      raise SystemLogManagerException('Thread is not running.')
    self._aborted.set()
    self._kick.set()
    self._sync_thread.join()
    self._sync_thread = None
    logging.info('Stopped sync thread.')

  def _RsyncDestination(self):
    """Gets rsync destination including server url, module, and folder name."""
    url = (shopfloor.get_server_url() or
           shopfloor.detect_default_server_url())
    proxy = shopfloor.get_instance(detect=True, timeout=self._shopfloor_timeout)
    factory_log_port = proxy.GetFactoryLogPort()
    folder_name = ('%s_%s' %
        (event_log.GetDeviceId().replace(':', ''), event_log.GetReimageId()))
    return ['rsync://%s:%s/system_logs/%s' %
            (urlparse(url).hostname, factory_log_port, folder_name)]

  def _ClearLogs(self):
    """Clears system logs listed in _clear_log_paths."""
    file_list = sum([glob.glob(x) for x in self._clear_log_paths], [])
    for f in file_list:
      try:
        os.unlink(f)
      except:  # pylint: disable=W0702
        logging.exception('Fail to remove file %s', f)

  def _SyncLogs(self, extra_files, callback, abort_time):
    """Syncs system logs and extra files to server with a callback.

    If the threads gets kicked, terminates the running subprocess.
    If rsync takes too long and exceeds abort_time, terminates the running
    subprocess.

    Args:
      extra_files: A list of extra files to sync.
      callback: A callback function to call after sync succeeds.
      abort_time: The time to abort rsync subprocess if abort_time is not None.
    """
    logging.debug('start _SyncLogs')
    rsync_command = ['rsync', '-azR', '--stats', '--chmod=o-t',
                     '--timeout=%s' % self._rsync_io_timeout]
    rsync_command += sum([glob.glob(x) for x in self._sync_log_paths], [])
    rsync_command += extra_files
    rsync_command += self._RsyncDestination()

    rsync = Spawn(rsync_command, ignore_stdout=True, ignore_stderr=True)
    while rsync.poll() is None:
      logging.debug('poll once')
      self._kick.wait(self._polling_period)
      # If there comes a kick event, rsync subprocess is aborted here and
      # kick event is processed later in _RunForever.
      # Aborts rsync if rsync takes too long and exceeds abort_time.
      if self._kick.isSet() or (abort_time and time.time() > abort_time):
        TerminateOrKillProcess(rsync)
        logging.warning('System log rsync aborted.')
        return
    if rsync.returncode:
      logging.error('Factory log rsync returned status %d',
                    rsync.returncode)
    else:
      # rsync succeeded, invoke callback function.
      logging.info('rsync succeeded')
      if callback:
        callback(extra_files)

  def _RunForever(self):
    """Syncs system logs periodically and syncs upon being kicked.

    If _sync_period_sec is None, manager will only sync upon being kicked.
    Set abort time for _SyncLogs only if _sync_period_sec is not None.
    """
    while True:
      self._kick.wait(self._sync_period_sec)
      # Stores the argument from kick event and fires later.
      extra_files, callback = self._extra_files, self._callback
      self._extra_files, self._callback = [], None
      self._kick.clear()
      if self._aborted.isSet():
        return
      try:
        self._ClearLogs()
        if self._sync_period_sec:
          abort_time = time.time() + self._sync_period_sec
        else:
          abort_time = None
        self._SyncLogs(extra_files, callback, abort_time)
      except:  # pylint: disable=W0702
        logging.warning(
          'Unable to sync system logs to shopfloor server: %s',
          '\n'.join(traceback.format_exception_only(
              *sys.exc_info()[:2])).strip())
