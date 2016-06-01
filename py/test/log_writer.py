# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Write testlog JSON logs to disk."""

import json
import logging
import os
import threading
import time

from uuid import uuid4

import factory_common  # pylint: disable=W0611
from cros.factory.test.env import paths
from cros.factory.utils import platform_utils
from cros.factory.utils import file_utils
from cros.factory.utils import sys_utils


FileLock = platform_utils.GetProvider('FileLock')


# The location to store the device ID file should be a place that is
# less likely to be deleted.
DEVICE_ID_PATH = os.path.join(paths.GetFactoryRoot(), 'testlog_device_id')

WLAN0_MAC_PATH = '/sys/class/net/wlan0/address'
MLAN0_MAC_PATH = '/sys/class/net/mlan0/address'
# TODO(kitching): Add CPUID for Intel devices?
DEVICE_ID_SEARCH_PATHS = [WLAN0_MAC_PATH, MLAN0_MAC_PATH]

STATE_DIR = paths.GetStateRoot()

# Path to use to persist image ID.
REIMAGE_ID_PATH = os.path.join(STATE_DIR, 'testlog_reimage_id')

# File containing the number of times Goofy has been initialized.
INIT_COUNT_PATH = os.path.join(STATE_DIR, 'init_count')

# The /var/factory/log directory (or equivalent if in the chroot).
LOG_DIR = paths.GetLogRoot()

# The main JSON file. It will be ingested by a local Instalog instance.
TESTLOG_PATH = os.path.join(LOG_DIR, 'testlog.json')

# The /var/run directory (or something writable by us if in the chroot).
RUN_DIR = os.path.join(
    paths.GetFactoryRoot('run') if sys_utils.InChroot() else '/var/run',
    'factory')

# File containing the next sequence number to write. This is in
# /var/run so it is cleared on each boot.
SEQUENCE_PATH = os.path.join(RUN_DIR, 'testlog_seq')

# Each boot, the sequence number increases by this amount, to try to
# help ensure monotonicity.
#
# For example, say we write events #55 and #56 to the event file and
# sync them to the Shopfloor server, but then we have a power problem
# and then lose those events before they are completely flushed to
# disk. On reboot, the last event we will find in the events file is
# #54, so if we started again with #55 we would violate monotonicity
# in the Shopfloor server record. But this way we will start with
# sequence number #1000055.
#
# This is not bulletproof: we could write and sync event #1000055,
# then have a similar power problem, and on the next reboot write and
# sync event #1000055 again. But this is much more unlikely than the
# above scenario.
SEQ_INCREMENT_ON_BOOT = 1000000

# Cache the DEVICE_ID and REIMAGE_ID after being read from disk or
# after being generated (if they do not yet exist).
_device_id = None
_reimage_id = None

# A global log writer. Since each test is invoked separately as a
# process, each test will have their own "global" log writer with
# correct context. Goofy will also have its separate log writer.
# Use the lock to avoid two threads creating two LogWriters.
_global_log_writer = None
_log_writer_lock = threading.Lock()


def Log(event):
  """Logs the event using the global log writer.

  This function is essentially a wrapper around LogWriter.Log(). It
  creates or reuses the global log writer and calls the LogWriter.Log()
  function. Note that this should only be used in pytests, which are
  spawned as separate processes.
  """
  GetGlobalLogWriter().Log(event)


def GetGlobalLogWriter():
  """Gets the singleton instance of the global log writer.

  The global log writer obtains the current running test's uuid from the
  environment variable CROS_FACTORY_TEST_PARENT_INVOCATION and initializes
  LogWriter appropriately.

  Raises:
    ValueError: if the test path is not defined
  """
  global _global_log_writer  # pylint: disable=W0603

  if _global_log_writer is None:
    with _log_writer_lock:
      if _global_log_writer is None:
        test_run_id = os.environ.get(
            'CROS_FACTORY_TEST_PARENT_INVOCATION', None)
        _global_log_writer = LogWriter(test_run_id=test_run_id)

  return _global_log_writer


def GetDeviceID():
  """Returns the device ID.

  The device ID is created and stored when this function is first called
  on a device after imaging/reimaging. The result is stored in
  DEVICE_ID_PATH and is used for all future references. If DEVICE_ID_PATH
  does not exist, it is obtained from the first successful read from
  DEVICE_ID_SEARCH_PATHS. If none is available, the ID is generated.

  Note that ideally a device ID does not change for one "device". However,
  in the case that the read result from DEVICE_ID_SEARCH_PATHS changed (e.g.
  caused by firmware update, change of components) AND the device is reimaged,
  the device ID will change.
  """
  with _log_writer_lock:
    global _device_id  # pylint: disable=W0603
    if _device_id:
      return _device_id

    # Always respect the device ID recorded in DEVICE_ID_PATH first.
    if os.path.exists(DEVICE_ID_PATH):
      _device_id = open(DEVICE_ID_PATH).read().strip()
      if _device_id:
        return _device_id

    # Find or generate device ID from the search path.
    for path in DEVICE_ID_SEARCH_PATHS:
      if os.path.exists(path):
        _device_id = open(path).read().strip()
        if _device_id:
          break
    else:
      _device_id = str(uuid4())
      logging.warning('No device_id available yet: generated %s', _device_id)

    # Save the device ID to DEVICE_ID_PATH for future reloading.
    file_utils.TryMakeDirs(os.path.dirname(DEVICE_ID_PATH))
    with open(DEVICE_ID_PATH, 'w') as f:
      f.write(_device_id)
      f.flush()
      os.fsync(f)

    return _device_id


def GetReimageID():
  """Returns the reimage ID.

  This is stored in REIMAGE_ID_PATH; one is generated if not available.
  """
  with _log_writer_lock:
    global _reimage_id  # pylint: disable=W0603
    if not _reimage_id:
      if os.path.exists(REIMAGE_ID_PATH):
        _reimage_id = open(REIMAGE_ID_PATH).read().strip()
      if not _reimage_id:
        _reimage_id = str(uuid4())
        logging.info('No reimage_id available yet: generated %s', _reimage_id)

        # Save the reimage ID to REIMAGE_ID_PATH for future reloading.
        file_utils.TryMakeDirs(os.path.dirname(REIMAGE_ID_PATH))
        with open(REIMAGE_ID_PATH, 'w') as f:
          f.write(_reimage_id)
          f.flush()
          os.fsync(f)
    return _reimage_id


def GetInitCount():
  """Returns the current init count (or -1 if not available)."""
  try:
    return int(open(INIT_COUNT_PATH).read())
  except (IOError, ValueError):
    return -1


def IncrementInitCount():
  """Increments the init count.

  Creates the init count file if it does not already exist.
  """
  init_count = GetInitCount() + 1

  logging.info('Goofy init count = %d', init_count)

  file_utils.TryMakeDirs(os.path.dirname(INIT_COUNT_PATH))
  with open(INIT_COUNT_PATH, 'w') as f:
    f.write('%d' % init_count)
    f.flush()
    os.fsync(f.fileno())


class LogWriter(object):
  def __init__(self, test_run_id=None, seq=None):
    self.test_run_id = test_run_id
    self.json_log = JSONLogFile(TESTLOG_PATH)
    self.seq = seq or GlobalSeq(
        SEQUENCE_PATH, recovery_fn=self.json_log.RecoverSeq)

  def Close(self):
    self.json_log.Close()

  def Log(self, event):
    with self.json_log:
      self._LogUnlocked(event)

  def _LogUnlocked(self, event):
    event.Populate({
        'seq': self.seq.Next(),
        'stationDeviceId': GetDeviceID(),
        'stationReimageId': GetReimageID()})
    if self.test_run_id:
      # Currently ignored for events which don't have this field.
      # TODO(kitching): Figure out a way to add this field only when
      # necessary.
      event.Populate({'testRunId': self.test_run_id})
    line = event.ToJSON() + '\n'
    self.json_log.Log(line)
    return line


class ReentrantFileLock(object):
  """Represents a reentrant file lock.

  Uses a file on disk to keep track of a lock, and provides __enter__ and
  __exit__ functions for use in `with` statements.

  File handle is exposed as self.file for a subclass to use.
  """

  def __init__(self, path, mode):
    self.path = path
    self.mode = mode
    self.opened = False
    self.file = None
    self._lock_count = 0
    self._lock = threading.Lock()

  def __enter__(self):
    """Locks the associated log file."""
    with self._lock:
      self._lock_count += 1
      if self._lock_count > 1:
        return
      self._OpenUnlocked()
      FileLock(self.file.fileno(), True)

  def __exit__(self, ex_type, value, tb):
    """Unlocks the associated log file."""
    del ex_type, value, tb
    with self._lock:
      self._lock_count -= 1
      if self._lock_count > 0:
        return
      FileLock(self.file.fileno(), False)

  def Close(self):
    """Closes associated log file.  Removes any outstanding locks."""
    if self.file:
      with self._lock:
        self.opened = False
        self.file.close()
        self.file = None
        self._lock_count = 0

  def _OpenUnlocked(self):
    parent_dir = os.path.dirname(self.path)
    if not os.path.exists(parent_dir):
      try:
        os.makedirs(parent_dir)
      except OSError:
        # Maybe someone else tried to create it simultaneously
        if not os.path.exists(parent_dir):
          raise

    if self.opened:
      return

    self.file = open(self.path, self.mode)
    self.opened = True


class JSONLogFile(ReentrantFileLock):
  """Represents a JSON log file on disk."""

  def __init__(self, path=TESTLOG_PATH):
    super(JSONLogFile, self).__init__(path=path, mode='a')

  def Log(self, data):
    with self:
      self.file.write(data)
      self.file.flush()
      os.fsync(self.file.fileno())

    return data

  def RecoverSeq(self):
    """Finds the next sequence number based on the log file.

    This is the current maximum sequence number (or 0 if none is found). Takes
    the last line as the most recent event.
    """
    try:
      if not os.path.exists(self.path) or os.path.getsize(self.path) == 0:
        # There is no log file, or it is empty. It's safe to start at 0.
        return 0
    except os.error:
      # If the size can't be accessed for some reason, let's still try to
      # continue to the recovery phase.
      pass

    try:
      with open(self.path) as f:
        last = None
        for last in f:
          pass
        max_seq = json.loads(last)['seq']
        return max_seq + 1
    except (os.error, ValueError):
      # This should really never happen; maybe the events file is
      # so corrupted that a read operation is failing.
      return None


class GlobalSeq(object):
  """Manages a global sequence number in a file.

  FileLock is used to ensure atomicity.

  Args:
    path: Path to the sequence number file (defaults to SEQUENCE_PATH).
    recovery_fn: Function to call when sequence number needs to be recovered.
    _after_read: A function to call immediately after reading the
                 sequence number (for testing).
    _after_write: A function to call immediately after writing the
                  sequence number (for testing).
  """

  def __init__(self, path=SEQUENCE_PATH, recovery_fn=None,
               _after_read=lambda: True, _after_write=lambda: True):
    self.seq_path = path
    self.recovery_fn = recovery_fn
    self._after_read = _after_read
    self._after_write = _after_write

    self._Create()

  def _Create(self):
    """Creates the file if it does not yet exist or is invalid."""
    # Need to use os.open, because Python's open does not support
    # O_RDWR | O_CREAT.
    file_utils.TryMakeDirs(os.path.dirname(self.seq_path))
    fd = os.open(self.seq_path, os.O_RDWR | os.O_CREAT)
    with os.fdopen(fd, 'r+') as f:
      FileLock(fd, True)
      contents = f.read()
      if contents:
        try:
          _ = int(contents)
          return  # It's all good.
        except ValueError:
          logging.exception(
              'Sequence number file %s contains non-integer %r',
              self.seq_path, contents)

      value = self._FindNextSequenceNumber()
      f.write(str(value))
      # Ensure the sequence file is flushed to disk.
      f.flush()
      os.fsync(fd)

    logging.info('Created global sequence file %s with sequence number %d',
                 self.seq_path, value)

  def _NextOrRaise(self):
    """Returns the next sequence number, raising an exception on failure."""
    with open(self.seq_path, 'r+') as f:
      # The file will be closed, and the lock freed, as soon as this
      # block goes out of scope.
      FileLock(f.fileno(), True)
      value = int(f.read())
      self._after_read()
      f.seek(0)
      f.write(str(value + 1))
      # Don't bother flushing to disk. If a reboot occurs before flushing, the
      # sequence number will be increased by SEQ_INCREMENT_ON_BOOT, maintaining
      # the monotonicity property.
    self._after_write()
    return value

  def _FindNextSequenceNumber(self):
    """Recovers the sequence number using our recovery_fn."""
    if self.recovery_fn is None:
      logging.info('No recovery function specified; resetting to 0')
      return 0

    recovery_seq = self.recovery_fn()

    if recovery_seq is None:
      # This should really never happen; maybe the events file is
      # so corrupted that a read operation is failing.
      logging.exception('Unable to find next sequence number from '
                        'events file; using system time in ms')
      return int(time.time() * 1000)

    elif recovery_seq == 0:
      # There is no log file. It's safe to start at 0.
      return recovery_seq

    else:
      return recovery_seq + SEQ_INCREMENT_ON_BOOT

  def Next(self):
    """Returns the next sequence number.

    This needs to be run in the context of the log file being locked.
    Otherwise, there's a chance that the same `seq` number will be produced
    by two separate processes.
    """
    try:
      return self._NextOrRaise()
    except (IOError, OSError, ValueError):
      logging.exception('Unable to read global sequence number from %s; '
                        'trying to re-create', self.seq_path)

    # This should really never happen (unless, say, some process
    # corrupts or deletes the file). Try our best to re-create it;
    # this is not completely safe but better than totally hosing the
    # machine. On failure, we're really screwed, so just propagate
    # any exception.
    file_utils.TryUnlink(self.seq_path)
    self._Create()
    return self._NextOrRaise()
