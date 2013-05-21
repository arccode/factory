# -*- coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Routines for producing event logs."""


import fcntl
import logging
import re
import os
import threading
import time
import yaml

from uuid import uuid4

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test import utils
from cros.factory.utils import file_utils


# A global event logger to log all events for a test. Since each
# test is invoked separately as a process, each test will have
# their own "global" event log with correct context.
_global_event_logger = None
_event_logger_lock = threading.Lock()
_default_event_logger_prefix = None

# The location to store the device ID file should be a place that is
# less likely to be deleted.
DEVICE_ID_PATH = os.path.join(factory.get_factory_root(), ".device_id")

EVENT_LOG_DIR = os.path.join(factory.get_state_root(), "events")
WLAN0_MAC_PATH = "/sys/class/net/wlan0/address"
MLAN0_MAC_PATH = "/sys/class/net/mlan0/address"
DEVICE_ID_SEARCH_PATHS = [WLAN0_MAC_PATH, MLAN0_MAC_PATH]

# Path to use to generate an image ID in case none exists (i.e.,
# this is the first time we're creating an event log).
REIMAGE_ID_PATH = os.path.join(EVENT_LOG_DIR, ".reimage_id")

# The /var/run directory (or something writable by us if in the chroot).
RUN_DIR = os.path.join(
    factory.get_factory_root('run') if utils.in_chroot() else "/var/run",
    'factory')

# File containing the next sequence number to write.  This is in
# /var/run so it is cleared on each boot.
SEQUENCE_PATH = os.path.join(RUN_DIR, "event_log_seq")

# The main events file.  Goofy will add "." + reimage_id to this
# filename when it synchronizes events to the shopfloor server.
EVENTS_PATH = os.path.join(EVENT_LOG_DIR, "events")

BOOT_SEQUENCE_PATH = os.path.join(EVENT_LOG_DIR, ".boot_sequence")

# Each boot, the sequence number increases by this amount, to try to
# help ensure monotonicity.
#
# For example, say we write events #55 and #56 to the event file and
# sync them to the shopfloor server, but then we have a power problem
# and then lose those events before they are completely flushed to
# disk.  On reboot, the last event we will find in the events file is
# #54, so if we started again with #55 we would violate monotonicity
# in the shopfloor server record.  But this way we will start with
# sequence number #1000055.
#
# This is not bulletproof: we could write and sync event #1000055,
# then have a similar power problem, and on the next reboot write and
# sync event #1000055 again.  But this is much more unlikely than the
# above scenario.
SEQ_INCREMENT_ON_BOOT = 1000000

# Regexp matching the sequence number in the events file.
SEQ_RE = re.compile("^SEQ: (\d+)$")

PREFIX_RE = re.compile("^[a-zA-Z0-9_\.]+$")
EVENT_NAME_RE = re.compile(r"^[a-zA-Z_]\w*$")
EVENT_KEY_RE = EVENT_NAME_RE

# Sync markers.
#
# We will add SYNC_MARKER ("#s\n") to the end of each event.  This is
# a YAML comment so it does not affect the semantic value of the event
# at all.
#
# If sync markers are enabled, the event log watcher will replace the
# last "#s" with "#S" after sync.  If it then restarts, it will look
# for the last "#S" and use that sequence to remember where to resume
# syncing.  This will look like:
#
#   ---
#   SEQ: 1
#   foo: a
#   #s
#   ---
#   SEQ: 2
#   foo: b
#   #S
#   ---
#   SEQ: 3
#   foo: c
#   #s
#   ---
#
# In this case, events 1 and 2 have been synced (since the last #S entry is
# in event 2).  Event 3 has not yet been synced.
SYNC_MARKER = '#s\n'
SYNC_MARKER_COMPLETE = '#S\n'
assert len(SYNC_MARKER) == len(SYNC_MARKER_COMPLETE)

# The strings that the event log watcher will search and replace with
# to mark a portion of the log as synced.
SYNC_MARKER_SEARCH = '\n' + SYNC_MARKER + '---\n'
SYNC_MARKER_REPLACE = '\n' + SYNC_MARKER_COMPLETE + '---\n'

# Since gooftool uses this.
TimeString = utils.TimeString

device_id = None
reimage_id = None


class EventLogException(Exception):
  pass


class FloatDigit(object):
  """Dumps float to yaml with specified digits under decimal point.

  This class has customized __repr__ so it can be used in yaml representer.
  Usage is like:
  print yaml.dump(FloatDigit(0.12345, 4))
  0.1235
  """
  def __init__(self, value, digit):
    self._value = value
    self._digit = digit

  def __repr__(self):
    return ("%%.0%df" % self._digit) % self._value


def float_repr(dumper, data):
  """The representer for float type."""
  return dumper.represent_scalar(u'tag:yaml.org,2002:float', repr(data))


# Add customized representer for type FloatDigit.
yaml.add_representer(FloatDigit, float_repr)


def TimedUuid():
  """Returns a UUID that is roughly sorted by time.

  The first 8 hexits are replaced by the current time in 100ths of a
  second, mod 2**32.  This will roll over once every 490 days, but it
  will cause UUIDs to be sorted by time in the vast majority of cases
  (handy for ls'ing directories); and it still contains far more than
  enough randomness to remain unique.
  """
  return ("%08x" % (int(time.time() * 100) & 0xFFFFFFFF) +
          str(uuid4())[8:])


def YamlDump(structured_data):
  """Wraps yaml.dump to make calling convention consistent."""
  return yaml.dump(structured_data,
                   default_flow_style=False,
                   allow_unicode=True)


def Log(event_name, **kwargs):
  """Logs the event using the global event logger.

  This function is essentially a wrapper around EventLog.Log(). It
  creates or reuses the global event logger and calls the EventLog.Log()
  function. Note that this should only be used in unit tests, which are
  spawned as separate processes.
  """

  GetGlobalLogger().Log(event_name, **kwargs)


def GetGlobalLogger():
  """Gets the singleton instance of the global event logger.

  The global event logger obtains path and uuid from the environment
  variables CROS_FACTORY_TEST_PATH and CROS_FACTORY_TEST_INVOCATION
  respectively. Initialize EventLog directly for customized parameters.

  Raises:
    ValueError: if the test path is not defined
  """

  global _global_event_logger  # pylint: disable=W0603

  if _global_event_logger is None:
    with _event_logger_lock:
      if _global_event_logger is None:
        path = (_default_event_logger_prefix or
               os.environ.get('CROS_FACTORY_TEST_PATH', None))
        if not path:
          raise ValueError("CROS_FACTORY_TEST_PATH environment"
            "variable is not set")
        uuid = os.environ.get('CROS_FACTORY_TEST_INVOCATION') or TimedUuid()
        _global_event_logger = EventLog(path, uuid)

  return _global_event_logger


def SetGlobalLoggerDefaultPrefix(prefix):
  """Sets the default prefix for the global logger.

  Note this function must be called before the global event logger is
  initialized (i.e. before GetGlobalLogger() is called).

  Args:
      prefix: String to identify this category of EventLog, to help
        humans differentiate between event log files (since UUIDs all
        look the same).  If string is not alphanumeric with period and
        underscore punctuation, raises ValueError.
  Raises:
      EventLogException: if the global event logger has been initialized
      ValueError: if the format of prefix is invalid
  """

  global _default_event_logger_prefix  # pylint: disable=W0603

  if not PREFIX_RE.match(prefix):
    raise ValueError("prefix %r must match re %s" % (
      prefix, PREFIX_RE.pattern))
  elif _global_event_logger:
    raise EventLogException(("Unable to set default prefix %r after "
      "initializing the global event logger") % prefix)

  _default_event_logger_prefix = prefix


def GetDeviceId():
  """Returns the device ID.

  The device ID is created and stored when this function is first called
  on a device after imaging/reimaging. The result is stored in
  DEVICE_ID_PATH and is used for all future references. If DEVICE_ID_PATH
  does not exist, it is obtained from the first successful read from
  DEVICE_ID_SEARCH_PATHS. If none is available, the id is generated.

  Note that ideally a device ID does not change for one "device". However,
  in the case that the read result from DEVICE_ID_SEARCH_PATHS changed (e.g.
  caused by firmware update, change of components) AND the device is reimaged,
  the device ID will change.
  """
  global device_id  # pylint: disable=W0603
  if device_id:
    return device_id

  # Always respect the device ID recorded in DEVICE_ID_PATH first.
  if os.path.exists(DEVICE_ID_PATH):
    device_id = open(DEVICE_ID_PATH).read().strip()
    if device_id:
      return device_id

  # Find or generate device ID from the search path.
  for path in DEVICE_ID_SEARCH_PATHS:
    if os.path.exists(path):
      device_id = open(path).read().strip()
      if device_id:
        break
  else:
    device_id = str(uuid4())
    logging.warning('No device_id available yet: generated %s', device_id)

  # Cache the device ID to DEVICE_ID_PATH for all future references.
  utils.TryMakeDirs(os.path.dirname(DEVICE_ID_PATH))
  with open(DEVICE_ID_PATH, "w") as f:
    print >> f, device_id
    f.flush()
    os.fdatasync(f)

  return device_id


def GetBootId():
  """Returns the boot ID."""
  return open("/proc/sys/kernel/random/boot_id", "r").read().strip()


def GetReimageId():
  """Returns the image ID.

  This is stored in REIMAGE_ID_PATH; one is generated if not available.
  """
  global reimage_id  # pylint: disable=W0603
  if not reimage_id:
    if os.path.exists(REIMAGE_ID_PATH):
      reimage_id = open(REIMAGE_ID_PATH).read().strip()
    if not reimage_id:
      reimage_id = str(TimedUuid())
      utils.TryMakeDirs(os.path.dirname(REIMAGE_ID_PATH))
      with open(REIMAGE_ID_PATH, "w") as f:
        print >> f, reimage_id
        f.flush()
        os.fdatasync(f)
      logging.info('No reimage_id available yet: generated %s', reimage_id)
  return reimage_id


def GetBootSequence():
  '''Returns the current boot sequence (or -1 if not available).'''
  try:
    return int(open(BOOT_SEQUENCE_PATH).read())
  except (IOError, ValueError):
    return -1


def IncrementBootSequence():
  '''Increments the boot sequence.

  Creates the boot sequence file if it does not already exist.
  '''
  boot_sequence = GetBootSequence() + 1

  logging.info('Boot sequence: %d', boot_sequence)

  utils.TryMakeDirs(os.path.dirname(BOOT_SEQUENCE_PATH))
  with open(BOOT_SEQUENCE_PATH, "w") as f:
    f.write('%d' % boot_sequence)
    f.flush()
    os.fdatasync(f.fileno())


class GlobalSeq(object):
  '''Manages a global sequence number in a file.

  flock is used to ensure atomicity.

  Args:
    path: Path to the sequence number file (defaults to SEQUENCE_PATH).
    _after_read: A function to call immediately after reading the
      sequence number (for testing).
  '''
  def __init__(self, path=None, _after_read=lambda: True):
    path = path or os.path.join(SEQUENCE_PATH)

    self.path = path
    self._after_read = _after_read

    self._Create()

  def _Create(self):
    '''Creates the file if it does not yet exist or is invalid.'''
    # Need to use os.open, because Python's open does not support
    # O_RDWR | O_CREAT.
    utils.TryMakeDirs(os.path.dirname(self.path))
    fd = os.open(self.path, os.O_RDWR | os.O_CREAT)
    with os.fdopen(fd, 'r+') as f:
      fcntl.flock(fd, fcntl.LOCK_EX)
      contents = f.read()
      if contents:
        try:
          dummy_value = int(contents)
          return  # It's all good
        except ValueError:
          logging.exception(
              'Sequence number file %s contains non-integer %r',
              self.path, dummy_value)

      value = self._FindNextSequenceNumber()
      f.write(str(value))
      f.flush()
      os.fdatasync(fd)

    logging.info('Created global sequence file %s with sequence number %d',
                 self.path, value)

  def _NextOrRaise(self):
    '''Returns the next sequence number, raising an exception on failure.'''
    with open(self.path, 'r+') as f:
      # The file will be closed, and the lock freed, as soon as this
      # block goes out of scope.
      fcntl.flock(f.fileno(), fcntl.LOCK_EX)
      # Now the FD will be closed/unlocked as soon as we go out of
      # scope.
      value = int(f.read())
      self._after_read()
      f.seek(0)
      f.write(str(value + 1))
      return value

  def Next(self):
    '''Returns the next sequence number.'''
    try:
      return self._NextOrRaise()
    except (IOError, OSError, ValueError):
      logging.exception('Unable to read global sequence number from %s; '
                        'trying to re-create', self.path)

    # This should really never happen (unless, say, some process
    # corrupts or deletes the file).  Try our best to re-create it;
    # this is not completely safe but better than totally hosing the
    # machine.  On failure, we're really screwed, so just propagate
    # any exception.
    file_utils.TryUnlink(self.path)
    self._Create()
    return self._NextOrRaise()

  def _FindNextSequenceNumber(self):
    '''Finds the next sequence number based on the event log file.

    This is the current maximum sequence number (or 0 if none is found)
    plus SEQ_INCREMENT_ON_BOOT.  We do not perform YAML parsing on the
    file; rather we just literally look for a line of the format SEQ_RE.

    A possible optimization would be to only look only in the last (say)
    100KB of the events file.

    Args:
      path: The path to examine (defaults to EVENTS_PATH).
    '''
    if not os.path.exists(EVENTS_PATH):
      # There is no events file.  It's safe to start at 0.
      return 0

    try:
      max_seq = 0

      for l in open(EVENTS_PATH).readlines():
        # Optimization to avoid needing to evaluate the regexp for each line
        if not l.startswith('SEQ'):
          continue
        match = SEQ_RE.match(l)
        if match:
          max_seq = max(max_seq, int(match.group(1)))

      return max_seq + SEQ_INCREMENT_ON_BOOT + 1
    except:  # pylint: disable=W0702
      # This should really never happen; maybe the events file is
      # so corrupted that a read operation is failing.
      logging.exception('Unable to find next sequence number from '
                        'events file; using system time in ms')
      return int(time.time() * 1000)

class EventLog(object):
  """Event logger.

  Properties:
    lock: A lock guarding all properties.
    file: The file object for logging.
    prefix: The prefix for the log file.
    seq: The current sequence number.
    log_id: The ID of the log file.
  """

  @staticmethod
  def ForAutoTest():
    """Deprecated, please use event_log.GetGlobalLogger() instead.

    Creates an EventLog object for the running autotest."""

    path = os.environ.get('CROS_FACTORY_TEST_PATH', 'autotest')
    uuid = os.environ.get('CROS_FACTORY_TEST_INVOCATION') or TimedUuid()
    return EventLog(path, uuid)

  def __init__(self, prefix, log_id=None, defer=True, seq=None, suppress=False):
    """Creates a new event logger, returning an EventLog instance.

    This always logs to the EVENTS_PATH file.  The file will be
    initialized with a preamble that includes the following fields:
     - device_id - Unique per device (eg, MAC addr).
     - reimage_id - Unique each time device is imaged.
     - log_id - Unique for each EventLog object.

    Due to the generation of device and image IDs, the creation of the *first*
    EventLog object is not thread-safe (i.e., one must be constructed completely
    before any others can be constructed in other threads or processes).  After
    that, construction of EventLogs and all EventLog operations are thread-safe.

    Args:
      prefix: String to identify this category of EventLog, to help
        humans differentiate between event log files (since UUIDs all
        look the same).  If string is not alphanumeric with period and
        underscore punctuation, raises ValueError.
      log_id: A UUID for the log (or None, in which case TimedUuid() is used)
      defer: If True, then the file will not be written until the first
        event is logged (if ever).
      seq: The GlobalSeq object to use (creates a new one if None).
      suppress: True to suppress event logging, turning this into a dummy
        object.  (This may also be be specified by directly modifying the
        suppress property.)
    """
    self.file = None
    self.suppress = suppress
    if not PREFIX_RE.match(prefix):
      raise ValueError("prefix %r must match re %s" % (
        prefix, PREFIX_RE.pattern))
    self.prefix = prefix
    self.lock = threading.Lock()
    self.seq = seq or GlobalSeq()
    self.log_id = log_id or TimedUuid()
    self.opened = False

    if not self.suppress and not defer:
      self._OpenUnlocked()

  def Close(self):
    """Closes associated log file."""
    with self.lock:
      if self.file:
        self.file.close()
        self.file = None

  def Log(self, event_name, **kwargs):
    """Writes new event stanza to log file, with consistent metadata.

    Appends a stanza contain the following fields to the log:
      TIME: Formatted as per TimeString().
      SEQ: Monotonically increating counter.
      EVENT: From event_name input.
      LOG_ID: Log ID from when the logger was created.
      PREFIX: Prefix from when the logger was created.
      ... - Other fields from kwargs.

    Stanzas are terminated by "---\n".

    event_name and kwarg keys must all start with [a-zA-Z_] and
    contain only [a-zA-Z0-9_] (like Python identifiers).

    Args:
      event_name: Used to identify event field.
      kwargs: Dict of additional fields for inclusion in the event
        stanza.  Field keys must be alphanumeric and lowercase. Field
        values will be automatically yaml-ified.  Other data
        types will result in a ValueError.
    """
    if self.suppress:
      return

    with self.lock:
      self._LogUnlocked(event_name, **kwargs)

  def _OpenUnlocked(self):
    """Opens the file and writes the preamble (if not already open).

    Requires that the lock has already been acquired.
    """
    parent_dir = os.path.dirname(EVENTS_PATH)
    if not os.path.exists(parent_dir):
      try:
        os.makedirs(parent_dir)
      except:  # pylint: disable=W0702
        # Maybe someone else tried to create it simultaneously
        if not os.path.exists(parent_dir):
          raise

    if self.opened:
      return
    self.opened = True

    logging.info('Logging events for %s into %s', self.prefix, EVENTS_PATH)

    self.file = open(EVENTS_PATH, "a")
    self._LogUnlocked("preamble",
                      LOG_ID=self.log_id,
                      PREFIX=self.prefix,
                      boot_id=GetBootId(),
                      device_id=GetDeviceId(),
                      reimage_id=GetReimageId(),
                      boot_sequence=GetBootSequence(),
                      factory_md5sum=factory.get_current_md5sum())

  def _LogUnlocked(self, event_name, **kwargs):
    """Same as Log, but requires that the lock has already been acquired.

    See Log() for Args and Returns.
    """
    self._OpenUnlocked()

    if self.file is None:
      raise IOError, "cannot append to closed file for prefix %r" % (
        self.prefix)
    if not EVENT_NAME_RE.match(event_name):
      raise ValueError("event_name %r must match %s" % (
        event_name, EVENT_NAME_RE.pattern))
    for k in kwargs:
      if not EVENT_KEY_RE.match(k):
        raise ValueError("key %r must match re %s" % (
          k, EVENT_KEY_RE.pattern))
    data = {
        "EVENT": event_name,
        "SEQ": self.seq.Next(),
        "TIME": utils.TimeString(),
        "LOG_ID": self.log_id,
        "PREFIX": self.prefix,
        }
    data.update(kwargs)
    yaml_data = YamlDump(data) + SYNC_MARKER + "---\n"
    fcntl.flock(self.file.fileno(), fcntl.LOCK_EX)
    try:
      self.file.write(yaml_data)
      self.file.flush()
    finally:
      fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
    os.fdatasync(self.file.fileno())
