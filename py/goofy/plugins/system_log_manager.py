# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""SystemLogManager scans system logs periodically and clear/sync them."""


from collections import namedtuple
import glob
import logging
import os
import queue
import shutil
import threading
import time
import urllib.parse

from cros.factory.goofy.plugins import plugin
from cros.factory.test.env import paths
from cros.factory.test import server_proxy
from cros.factory.test import session
from cros.factory.utils.debug_utils import CatchException
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils.process_utils import TerminateOrKillProcess
from cros.factory.utils import time_utils
from cros.factory.utils import type_utils


KickRequest = namedtuple('KickRequest',
                         ['extra_files', 'callback', 'clear_only'])


MIN_SYNC_LOG_PERIOD_SECS = 120


MAX_CRASH_FILE_SIZE = 64 * 1024


class SystemLogManagerException(Exception):
  """Exception for SystemLogManager."""


class SystemLogManager(plugin.Plugin):
  """The manager that takes care of system log files.

  Properties set from __init__ arguments:
    sync_log_paths: A list of log paths to sync.
    sync_log_period_secs: The time period in seconds between consecutive syncs.
      Set it to None to disable periodic syncs. If it is not None, it should be
      larger than MIN_SYNC_LOG_PERIOD_SECS.
    scan_log_period_secs: The time period in seconds between consecutive scans.
      A scan includes clearing logs and optionally syncing logs.
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
    enable_foreground_sync: A boolean flag to indicate if user can run
      `KickToSync()` to request sync explicitly.

  Other properties:
    main_thread: The thread that scans logs periodically.
    aborted: The event to abort main_thread.
    queue: The queue to store all the sync requests.
  """

  def __init__(self, goofy, sync_log_paths, sync_log_period_secs=300,
               scan_log_period_secs=120,
               rsync_io_timeout=20, polling_period=1, clear_log_paths=None,
               clear_log_excluded_paths=None, enable_foreground_sync=True):
    super(SystemLogManager, self).__init__(goofy)
    self._sync_log_paths = sync_log_paths
    self._sync_log_period_secs = sync_log_period_secs
    self._scan_log_period_secs = scan_log_period_secs
    self._rsync_io_timeout = rsync_io_timeout
    self._polling_period = polling_period
    self._clear_log_paths = clear_log_paths if clear_log_paths else []
    self._clear_log_excluded_paths = (
        clear_log_excluded_paths if clear_log_excluded_paths else [])
    self.enable_foreground_sync = enable_foreground_sync

    self._main_thread = None
    self._aborted = threading.Event()
    self._queue = queue.Queue()
    self._suppress_periodic_server_messages = False

    # For unittest stubbing
    self._timer = time.time

    self._CheckSettings()

  def _CheckSettings(self):
    """Checks the parameters are valid."""
    if self._sync_log_period_secs:
      if self._sync_log_period_secs < MIN_SYNC_LOG_PERIOD_SECS:
        raise SystemLogManagerException(
            'sync_log_period_secs should not'
            ' be less than %d.' % MIN_SYNC_LOG_PERIOD_SECS)
      if self._scan_log_period_secs > self._sync_log_period_secs:
        raise SystemLogManagerException(
            'scan_log_period_secs should not'
            ' be greater than sync_log_period_seconds.')
    for list_name in ['_clear_log_paths', '_clear_log_excluded_paths']:
      list_attribute = getattr(self, list_name)
      if list_attribute and not isinstance(list_attribute, list):
        raise SystemLogManagerException('%r should be a list.' % list_name)
    if self._clear_log_paths and self._sync_log_paths:
      if set(self._clear_log_paths) & set(self._sync_log_paths):
        raise SystemLogManagerException('clear_log_paths should not be '
                                        'overlapped with sync_log_paths.')
    if self._clear_log_paths and self._clear_log_excluded_paths:
      if set(self._clear_log_paths) & set(self._clear_log_excluded_paths):
        raise SystemLogManagerException(
            'clear_log_paths should not be '
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
    if not self.enable_foreground_sync:
      return
    if not self.IsThreadRunning():
      raise SystemLogManagerException('Thread is not running.')
    if extra_files is None:
      extra_files = []
    self._queue.put(KickRequest(extra_files, callback, False))
    logging.debug('Puts extra_files: %r.', extra_files)

  @type_utils.Overrides
  def OnStart(self):
    """Starts SystemLogManager _main_thread with _RunForever method."""
    logging.info('Start SystemLogManager thread.')
    self._FindKcrash()
    self._ClearLogs()
    self._main_thread = threading.Thread(target=self._RunForever,
                                         name='SystemLogManager')
    self._main_thread.start()

  @type_utils.Overrides
  def OnStop(self):
    """Stops SystemLogManager _main_thread."""
    logging.debug('Sets aborted event to SystemLogManager main thread.')
    self._aborted.set()
    # Puts a request to kick _main_thread.
    self._queue.put(KickRequest([], None, False))
    self._main_thread.join()
    self._main_thread = None
    logging.info('SystemLogManager main thread stopped.')

  def _RsyncDestination(self):
    """Gets rsync destination including server url, module, and folder name.

    Returns:
      The rsync destination path for system logs.
    """
    url = server_proxy.GetServerURL()
    proxy = server_proxy.GetServerProxy()
    factory_log_port = proxy.GetFactoryLogPort()
    folder_name = session.GetDeviceID()
    return ['rsync://%s:%s/system_logs/%s' %
            (urllib.parse.urlparse(url).hostname, factory_log_port,
             folder_name)]

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
      except Exception:
        logging.exception('Fails to remove file %s.', f)
    logging.debug('Logs cleared.')

  @CatchException('SystemLogManager')
  def _SyncLogs(self, extra_files, callback, abort_time, periodic=False):
    """Wrapper of _SyncLogsImpl.

    Handles exception differently for periodic and non-periodic case.
    Error messages for periodic case will only be shown once.

    Args:
      extra_files: A list of extra files to sync.
      callback: A callback function to call after sync succeeds.
      abort_time: The time to abort rsync subprocess if abort_time is not None.
      periodic: This is a periodic sync.
    """
    try:
      self._SyncLogsImpl(extra_files, callback, abort_time)
    except Exception:
      if not periodic:
        raise
      if not self._suppress_periodic_server_messages:
        logging.warning(
            'Suppress periodic server error messages after the first one.')
        self._suppress_periodic_server_messages = True
        raise

  def _SyncLogsImpl(self, extra_files, callback, abort_time):
    """Syncs system logs and extra files to server with a callback.

    If the threads gets kicked, terminates the running subprocess.
    If rsync takes too long and exceeds abort_time, terminates the running
    subprocess.

    Args:
      extra_files: A list of extra files to sync.
      callback: A callback function to call after sync succeeds.
      abort_time: The time to abort rsync subprocess if abort_time is not None.
    """
    logging.debug('Starts _SyncLogsImpl.')
    # If in periodic sync, show error messages if
    # _suppress_periodic_server_message is not set.
    # If not in periodic sync, always show error messages.
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
      if self._aborted.isSet() or (abort_time and self._timer() > abort_time):
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

      except queue.Empty:
        # clears obsolete logs.
        self._ClearLogs()

        # There is no sync request.
        # Syncs if periodic syncing is enabled and the time
        # difference from last_sync_time to current time is greater than
        # _sync_log_period_secs. Note that last_sync_time is the starting time
        # of the last sync, not the end time. Also, the last sync might fail.
        if (self._sync_log_period_secs and
            (last_sync_time is None or
             (self._timer() - last_sync_time > self._sync_log_period_secs))):
          last_sync_time = self._timer()
          self._SyncLogs([], None, self._timer() + self._scan_log_period_secs,
                         True)
      else:
        logging.debug('Gets a request with extra_files, callback, clear_only:'
                      '%r, %r, %r.', extra_files, callback, clear_only)
        # There is a request from queue. But it might be set from Stop().
        if self._aborted.isSet():
          self._queue.task_done()
          logging.info('SystemLogManager got aborted.')
          return

        # Always clears obsolete logs.
        self._ClearLogs()

        if not clear_only:
          # Syncs logs according to the request.
          last_sync_time = self._timer()
          self._SyncLogs(extra_files, callback,
                         self._timer() + self._scan_log_period_secs)
        self._queue.task_done()

  def _FindKcrash(self):
    """Finds kcrash files, logs them, and marks them as seen."""
    seen_crashes = set(self.goofy.state_instance.DataShelfGetValue(
        'seen_crashes', optional=True) or [])

    for path in glob.glob('/var/spool/crash/*'):
      if not os.path.isfile(path):
        continue
      if path in seen_crashes:
        continue
      try:
        stat = os.stat(path)
        mtime = time_utils.TimeString(stat.st_mtime)
        logging.info(
            'Found new crash file %s (%d bytes at %s)',
            path, stat.st_size, mtime)
        extra_log_args = {}

        try:
          _, ext = os.path.splitext(path)
          if ext in ['.kcrash', '.meta']:
            ext = ext.replace('.', '')
            with open(path) as f:
              data = f.read(MAX_CRASH_FILE_SIZE)
              tell = f.tell()
            logging.info(
                'Contents of %s%s:%s',
                path,
                ('' if tell == stat.st_size
                 else '(truncated to %d bytes)' % MAX_CRASH_FILE_SIZE),
                ('\n' + data).replace('\n', '\n  ' + ext + '> '))
            extra_log_args['data'] = data

            # Copy to /var/factory/kcrash for posterity
            kcrash_dir = os.path.join(paths.DATA_DIR, 'kcrash')
            file_utils.TryMakeDirs(kcrash_dir)
            shutil.copy(path, kcrash_dir)
            logging.info('Copied to %s',
                         os.path.join(kcrash_dir, os.path.basename(path)))
        finally:
          # Even if something goes wrong with the above, still try to
          # log to event log
          self.goofy.event_log.Log('crash_file',
                                   path=path, size=stat.st_size, mtime=mtime,
                                   **extra_log_args)
      except Exception:
        logging.exception('Unable to handle crash files %s', path)
      seen_crashes.add(path)

    self.goofy.state_instance.DataShelfSetValue(
        'seen_crashes', list(seen_crashes))
