# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Sequence generator for testlog's seq field."""

import json
import logging
import os
import time

from .utils import file_utils

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
FILELOCK_WAITSECS = 0.5

class SeqGenerator:
  """Maintains a monotonically increasing sequence in best effort.

  Currently, only support a sequence recovery (i.e. sequence file is missing
  from disk) for JSON format log. FileLock is used to prevent racing across
  different process.

  Args:
    path: Path to the sequence number file.
    log_file_path: Path to JSON log while recovery tried when absence of
        sequence number file.
    _after_read: A function to call immediately after reading the sequence
        number (for testing).
    _filelock_waitsecs: It needs to be longer if lots of threads / processes
        competing for the same sequence file. Half seconds should be sufficient
        for most of the cases (expecting 1000 log accesses per second). For
        special testing purposes, this can be tweaked.
  """
  def __init__(self, path, log_file_path, _after_read=lambda: True,
               _filelock_waitsecs=FILELOCK_WAITSECS):
    self.path = path
    self.log_file_path = log_file_path
    self._after_read = _after_read
    self._filelock_waitsecs = _filelock_waitsecs
    self._Create()

  def _Create(self):
    """Creates the file if it does not yet exist or is invalid."""
    file_utils.TryMakeDirs(os.path.dirname(self.path))

    with file_utils.FileLock(self.path, self._filelock_waitsecs):
      with open(self.path, 'r+') as f:  # FileLock verified the existence.
        contents = f.read()
        if contents:
          try:
            _ = int(contents)
            return  # It's all good.
          except ValueError:
            logging.exception(
                'Sequence number file %s contains non-integer %r',
                self.path, contents)

        value = self._FindNextSequenceNumber()
        f.write(str(value))

    logging.info('Created global sequence file %s with sequence number %d',
                 self.path, value)

  def _GetLastSeq(self):
    """Finds the next sequence number based on the log file.

    This is the current maximum sequence number (or 0 if none is found). Takes
    the last line as the most recent event.
    """
    try:
      if not self.log_file_path:
        # No log file is assigned for recovery purpose.
        logging.exception(
            'No JSON log file is assigned for recovery purpose. Starts from 0')
        return 0

      if (not os.path.exists(self.log_file_path) or
          os.path.getsize(self.log_file_path) == 0):
        # There is no log file, or it is empty. It's safe to start at 0.
        return 0
    except os.error:
      # If the size can't be accessed for some reason, let's still try to
      # continue to the recovery phase.
      pass

    try:
      max_seq = 0
      seq = None
      last_line = ''
      for l in open(self.log_file_path).readlines():
        # Attempt to load the JSON to get the seq.
        try:
          seq = int(json.loads(l)['seq'])
          max_seq = max(max_seq, seq)
        except (ValueError, KeyError):
          pass
        last_line = l
      if not seq:
        # This could potentially happen if the JSON file was very small
        # and every single line was corrupted.
        logging.exception('JSON file %s is corrupted, last line is %r',
                          self.log_file_path, last_line)
        return None
      return max_seq + 1
    except os.error:
      # This should really never happen; maybe the JSON file is
      # so corrupted that a read operation is failing.
      logging.exception('Failed to read JSON file %s', self.log_file_path)
      return None

  def _FindNextSequenceNumber(self):
    """Recovers the sequence number and add SEQ_INCREMENT_ON_BOOT."""
    recovery_seq = self._GetLastSeq()

    if recovery_seq is None:
      # This should really never happen; maybe the events file is
      # so corrupted that a read operation is failing.
      logging.exception('Unable to find next sequence number from '
                        'events file; using system time in ms')
      return int(time.time() * 1000)

    if recovery_seq == 0:
      # There is no log file. It's safe to start at 0.
      return recovery_seq

    return recovery_seq + SEQ_INCREMENT_ON_BOOT

  def _NextOrRaise(self):
    """Returns the next sequence number, raising an exception on failure."""
    with file_utils.FileLock(self.path, self._filelock_waitsecs):
      with open(self.path, 'r+') as f:
        # The file will be closed, and the lock freed, as soon as this
        # block goes out of scope.
        value = int(f.read())
        self._after_read()
        f.seek(0)
        f.write(str(value + 1))
      # Don't bother flushing to disk. If a reboot occurs before flushing, the
      # sequence number will be increased by SEQ_INCREMENT_ON_BOOT,
      # maintaining the monotonicity property.
    return value

  def Current(self):
    """Returns the last-used sequence number, or None on failure."""
    try:
      with file_utils.FileLock(self.path, self._filelock_waitsecs):
        with open(self.path, 'r') as f:
          value = int(f.read()) - 1
      return value
    except (IOError, OSError, ValueError):
      logging.exception('Unable to read global sequence number from %s; ',
                        self.path)
      return None

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
                        'trying to re-create', self.path)

    # This should really never happen (unless, say, some process
    # corrupts or deletes the file). Try our best to re-create it;
    # this is not completely safe but better than totally hosing the
    # machine. On failure, we're really screwed, so just propagate
    # any exception.
    file_utils.TryUnlink(self.path)
    self._Create()
    return self._NextOrRaise()
