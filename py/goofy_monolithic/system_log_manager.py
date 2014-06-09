# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""SystemLogManager scans system logs periodically and clear/sync them."""


import glob
import logging
import os
import Queue
import threading
import time
from collections import namedtuple
from urlparse import urlparse

import factory_common  # pylint: disable=W0611
from cros.factory import event_log
from cros.factory.test import shopfloor
from cros.factory.utils.debug_utils import CatchException
from cros.factory.utils.process_utils import Spawn, TerminateOrKillProcess

KickRequest = namedtuple('KickRequest',
                         ['extra_files', 'callback', 'clear_only'])


MIN_SYNC_LOG_PERIOD_SECS = 120


class SystemLogManagerException(Exception):
  """Exception for SystemLogManager."""
  pass


class SystemLogManager(object):
  """The manager that takes care of system log files.

  Properties set from __init__ arguments:
    sync_log_paths: A list of log paths to sync.
    sync_log_period_secs: The time period in seconds between consecutive syncs.
      Set it to None to disable periodic syncs. If it is not None, it should be
      larger than MIN_SYNC_LOG_PERIOD_SECS.
    scan_log_period_secs: The time period in seconds between consecutive scans.
      A scan includes clearing logs and optionally syncing logs.
    shopfloor_timeout: Timeout to get shopfloor instance.
    rsync_io_timeout: I/O timeout argument in rsync command. When file is
      large, system needs more time to compute the difference. Sets it to
      20 seconds which is enough to compute the difference on a 300M file.
    polling_period: The period to poll rsync subprocess.
    clear_log_paths: A list of log paths to clear. Each item in the list can be
      a pattern. E.g. ['/var/log/messages*', '/var/log/net.log',
                       '/var/log/connectivity.log'].
    clear_log_excluded_paths: A list of log path patterns to be excluded from
      clearing. E.g. ['/var/log/messages', '/var/log/messages.1',
                     '/var/log/messages.2'], then SystemLogManager will
      preserve these files while they match '/var/log/messages*' in
      clear_log_paths.

  Other properties:
    main_thread: The thread that scans logs periodically.
    aborted: The event to abort main_thread.
    queue: The queue to store all the sync requests.
  """
  def __init__(self, sync_log_paths, sync_log_period_secs=300,
               scan_log_period_secs=120, shopfloor_timeout=5,
               rsync_io_timeout=20, polling_period=1, clear_log_paths=None,
               clear_log_excluded_paths=None):
    self._sync_log_paths = sync_log_paths
    self._sync_log_period_secs = sync_log_period_secs
    self._scan_log_period_secs = scan_log_period_secs
    self._shopfloor_timeout = shopfloor_timeout
    self._rsync_io_timeout = rsync_io_timeout
    self._polling_period = polling_period
    self._clear_log_paths = clear_log_paths if clear_log_paths else []
    self._clear_log_excluded_paths = (
        clear_log_excluded_paths if clear_log_excluded_paths else [])

    self._main_thread = None
    self._aborted = threading.Event()
    self._queue = Queue.Queue()

    self._CheckSettings()

  def _CheckSettings(self):
    """Checks the parameters are valid."""
    if self._sync_log_period_secs:
      if self._sync_log_period_secs < MIN_SYNC_LOG_PERIOD_SECS:
        raise SystemLogManagerException('sync_log_period_secs should not'
            ' be less than %d.' % MIN_SYNC_LOG_PERIOD_SECS)
      if self._scan_log_period_secs > self._sync_log_period_secs:
        raise SystemLogManagerException('scan_log_period_secs should not'
            ' be greater than sync_log_period_seconds.')
    for list_name in ['_clear_log_paths', '_clear_log_excluded_paths']:
      list_attribute = getattr(self, list_name)
      if list_attribute and not isinstance(list_attribute, list):
        raise SystemLogManagerException('%r should be a list.', list_name)
    if self._clear_log_paths and self._sync_log_paths:
      if (set(self._clear_log_paths) & set(self._sync_log_paths)):
        raise SystemLogManagerException('clear_log_paths should not be '
            'overlapped with sync_log_paths.')
    if self._clear_log_paths and self._clear_log_excluded_paths:
      if set(self._clear_log_paths) & set(self._clear_log_excluded_paths):
        raise SystemLogManagerException('clear_log_paths should not be '
            'overlapped with clear_log_excluded_paths.')

  def IsThreadRunning(self):
    """Returns True if _main_thread is running."""
    return self._main_thread and self._main_thread.isAlive()

  def KickToClear(self):
    """Kicks _main_thread to clear logs.

    Stores the request into _queue and kicks _main_thread to handle the request.

    Raises:
      SystemLogManagerException: If thread is not running.
    """
    if not self.IsThreadRunning():
      raise SystemLogManagerException('Thread is not running.')
    self._queue.put(KickRequest([], None, True))
    logging.debug('Puts a clear request.')

  def KickToSync(self, extra_files=None, callback=None):
    """Kicks _main_thread to sync logs with extra files and a callbalk.

    Stores the request into _queue and kicks _main_thread to handle the request.
    SystemLogManager will clear logs, sync logs, and execute the callback.

    Args:
      extra_files: A list of extra files to sync.
      callback: A callback to call after sync succeeds. This is to serve the
        case such as deleting the files after syncing them to server.

    Raises:
      SystemLogManagerException: If thread is not running.
    """
    if not self.IsThreadRunning():
      raise SystemLogManagerException('Thread is not running.')
    if extra_files is None:
      extra_files = []
    self._queue.put(KickRequest(extra_files, callback, False))
    logging.debug('Puts extra_files: %r.', extra_files)

  def Start(self):
    """Starts SystemLogManager _main_thread with _RunForever method."""
    logging.info('Start SystemLogManager thread.')
    self._ClearLogs()
    self._main_thread = threading.Thread(target=self._RunForever,
                                         name='SystemLogManager')
    self._main_thread.start()

  def Stop(self):
    """Stops SystemLogManager _main_thread.

    Raises:
      SystemLogManagerException: If thread is not running.
    """
    if not self.IsThreadRunning():
      raise SystemLogManagerException('Thread is not running.')
    logging.debug('Sets aborted event to SystemLogManager main thread.')
    self._aborted.set()
    # Puts a request to kick _main_thread.
    self._queue.put(KickRequest([], None, False))
    self._main_thread.join()
    self._main_thread = None
    logging.info('SystemLogManager main thread stopped.')

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

  @CatchException('SystemLogManager')
  def _ClearLogs(self):
    """Clears system logs.

    Clear logs listed in _clear_log_paths, excluding files in
    _clear_log_excluded_paths.
    """
    clear_files = sum([glob.glob(x) for x in self._clear_log_paths], [])
    exclusive_files = sum(
        [glob.glob(x) for x in self._clear_log_excluded_paths], [])
    file_list = list(set(clear_files) - set(exclusive_files))
    logging.debug('Clearing %r', file_list)
    for f in file_list:
      try:
        os.unlink(f)
      except:  # pylint: disable=W0702
        logging.exception('Fails to remove file %s.', f)
    logging.debug('Logs cleared.')

  @CatchException('SystemLogManager')
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
    logging.debug('Starts _SyncLogs.')
    rsync_command = ['rsync', '-azR', '--stats', '--chmod=o-t',
                     '--timeout=%s' % self._rsync_io_timeout]
    rsync_command += sum([glob.glob(x) for x in self._sync_log_paths], [])
    rsync_command += extra_files
    rsync_command += self._RsyncDestination()

    rsync = Spawn(rsync_command, ignore_stdout=True, ignore_stderr=True)
    while rsync.poll() is None:
      logging.debug('Polls once.')
      self._aborted.wait(self._polling_period)
      # Aborts rsync if rsync takes too long and exceeds abort_time.
      if self._aborted.isSet() or (abort_time and time.time() > abort_time):
        TerminateOrKillProcess(rsync)
        logging.warning('System log rsync aborted.')
        return
    if rsync.returncode:
      logging.error('Factory log rsync returned status %d.',
                    rsync.returncode)
    else:
      # rsync succeeded, invoke callback function.
      logging.info('rsync succeeded.')
      if callback:
        callback(extra_files)

  def _RunForever(self):
    """The main method that SystemLogManager runs forever until being stopped.

    SystemLogManager clears system logs periodically and syncs them optionally.
    If user calls KickToSync method, SystemLogManager will clear logs and then
    deal with the request.
    If user calls KickToClear method, SystemLogManager will clear logs.
    """
    last_sync_time = None
    while True:
      try:
        extra_files, callback, clear_only = self._queue.get(
            block=True, timeout=self._scan_log_period_secs)

      except Queue.Empty:
        # clears obsolete logs.
        self._ClearLogs()

        # There is no sync request.
        # Syncs if periodic syncing is enabled and the time
        # difference from last_sync_time to current time is greater than
        # _sync_log_period_secs. Note that last_sync_time is the starting time
        # of the last sync, not the end time. Also, the last sync might fail.
        if (self._sync_log_period_secs and
            (last_sync_time is None or
             (time.time() - last_sync_time > self._sync_log_period_secs))):
          last_sync_time = time.time()
          self._SyncLogs([], None, time.time() + self._scan_log_period_secs)

      else:
        logging.debug('Gets a request with extra_files, callback, clear_only:'
                      '%r, %r, %r.', extra_files, callback, clear_only)
        # There is a request from queue. But it might be set from Stop().
        if self._aborted.isSet():
          self._queue.task_done()
          logging.info('SystemLogManager got aborted.')
          return

        else:
          # Always clears obsolete logs.
          self._ClearLogs()

          if not clear_only:
            # Syncs logs according to the request.
            last_sync_time = time.time()
            self._SyncLogs(extra_files, callback,
                           time.time() + self._scan_log_period_secs)
        self._queue.task_done()
