# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Routines for producing event logs."""


import logging
import os
import re
import threading
import time
import uuid

import yaml

from cros.factory.test.env import paths
from cros.factory.test import session
from cros.factory.utils import file_utils
from cros.factory.utils import platform_utils
from cros.factory.utils import time_utils


FileLock = platform_utils.GetProvider('FileLock')

# A global event logger to log all events for a test. Since each
# test is invoked separately as a process, each test will have
# their own "global" event log with correct context.
_global_event_logger = None
_event_logger_lock = threading.Lock()
_default_event_logger_prefix = None

EVENT_LOG_DIR = os.path.join(paths.DATA_STATE_DIR, "events")

# Path to use to generate an image ID in case none exists (i.e.,
# this is the first time we're creating an event log).
REIMAGE_ID_PATH = os.path.join(EVENT_LOG_DIR, ".reimage_id")

# The /run directory (or something writable by us if in the chroot).
RUN_DIR = os.path.join(paths.RUNTIME_VARIABLE_DATA_DIR, "factory")

# File containing the next sequence number to write.  This is in
# /run so it is cleared on each boot.
SEQUENCE_PATH = os.path.join(RUN_DIR, "event_log_seq")

# The main events file.  Goofy will add "." + reimage_id to this
# filename when it synchronizes events to the shopfloor server.
EVENTS_PATH = os.path.join(EVENT_LOG_DIR, "events")

BOOT_SEQUENCE_PATH = os.path.join(EVENT_LOG_DIR, ".boot_sequence")

# Cache the DEVICE_ID and REIMAGE_ID after being read from disk or
# after being generated (if they do not yet exist).
_device_id = None
_reimage_id = None

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
SEQ_RE = re.compile(r"^SEQ: (\d+)$")

# Regexp matching the prefix of events.
PREFIX_RE = re.compile(r"^([\w\:]+(?:-\d+)?\.?)+$")

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
SYNC_MARKER = "#s\n"
SYNC_MARKER_COMPLETE = "#S\n"
assert len(SYNC_MARKER) == len(SYNC_MARKER_COMPLETE)

# The strings that the event log watcher will search and replace with
# to mark a portion of the log as synced.
SYNC_MARKER_SEARCH = "\n" + SYNC_MARKER + "---\n"
SYNC_MARKER_REPLACE = "\n" + SYNC_MARKER_COMPLETE + "---\n"

# Since gooftool uses this.
TimeString = time_utils.TimeString


class EventLogException(Exception):
  pass


class FloatDigit:
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


def YamlFloatDigitRepresenter(dumper, data):
  """The representer for FloatDigit type."""
  return dumper.represent_scalar(u"tag:yaml.org,2002:float", repr(data))


def YamlObjectRepresenter(dumper, data):
  """The representer for a general object, output its attributes as as dict."""
  return dumper.represent_dict(data.__dict__)


CustomDumper = yaml.SafeDumper

# Add customized representer for type FloatDigit.
CustomDumper.add_representer(FloatDigit, YamlFloatDigitRepresenter)
# Add customized representers for the subclasses of native classes.
CustomDumper.add_multi_representer(dict, CustomDumper.represent_dict)
CustomDumper.add_multi_representer(list, CustomDumper.represent_list)
CustomDumper.add_multi_representer(str, CustomDumper.represent_str)
CustomDumper.add_multi_representer(tuple, CustomDumper.represent_list)
# Add customized representer for the rests, output its attributes as a dict.
CustomDumper.add_multi_representer(object, YamlObjectRepresenter)


def YamlDump(structured_data):
  """Wraps yaml.dump to make calling convention consistent."""
  return yaml.dump(structured_data,
                   default_flow_style=False,
                   allow_unicode=True,
                   Dumper=CustomDumper)


def Log(event_name, **kwargs):
  """Logs the event using the global event logger.

  This function is essentially a wrapper around EventLog.Log(). It
  creates or reuses the global event logger and calls the EventLog.Log()
  function. Note that this should only be used in pytests, which are
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

  global _global_event_logger  # pylint: disable=global-statement

  if _global_event_logger is None:
    with _event_logger_lock:
      if _global_event_logger is None:
        path = (_default_event_logger_prefix or
                os.environ.get("CROS_FACTORY_TEST_PATH", None))
        if not path:
          raise ValueError("CROS_FACTORY_TEST_PATH environment"
                           "variable is not set")
        test_uuid = (os.environ.get("CROS_FACTORY_TEST_INVOCATION") or
                     time_utils.TimedUUID())
        _global_event_logger = EventLog(path, test_uuid)

  return _global_event_logger


def SetGlobalLoggerDefaultPrefix(prefix):
  """Sets the default prefix for the global logger.

  Note this function must be called before the global event logger is
  initialized (i.e. before GetGlobalLogger() is called).

  Args:
      prefix: String to identify this category of EventLog, to help
        humans differentiate between event log files (since UUIDs all
        look the same).  If string does not match PREFIX_RE, raises ValueError.
  Raises:
      EventLogException: if the global event logger has been initialized
      ValueError: if the format of prefix is invalid
  """

  global _default_event_logger_prefix  # pylint: disable=global-statement

  if not PREFIX_RE.match(prefix):
    raise ValueError("prefix %r must match re %s" % (
        prefix, PREFIX_RE.pattern))
  if _global_event_logger:
    raise EventLogException(("Unable to set default prefix %r after "
                             "initializing the global event logger") % prefix)

  _default_event_logger_prefix = prefix


def GetReimageId():
  """Returns the reimage ID.

  This is stored in REIMAGE_ID_PATH; one is generated if not available.
  """
  with _event_logger_lock:
    global _reimage_id  # pylint: disable=global-statement
    if not _reimage_id:
      if os.path.exists(REIMAGE_ID_PATH):
        _reimage_id = open(REIMAGE_ID_PATH).read().strip()
      if not _reimage_id:
        _reimage_id = str(uuid.uuid4())
        logging.info('No reimage_id available yet: generated %s', _reimage_id)

        # Save the reimage ID to REIMAGE_ID_PATH for future reloading.
        file_utils.TryMakeDirs(os.path.dirname(REIMAGE_ID_PATH))
        with open(REIMAGE_ID_PATH, 'w') as f:
          f.write(_reimage_id)
          f.flush()
          os.fsync(f)
    return _reimage_id


def GetBootSequence():
  return session.GetInitCount(path=BOOT_SEQUENCE_PATH)


def IncrementBootSequence():
  return session.IncrementInitCount(path=BOOT_SEQUENCE_PATH)


def GetBootId():
  return session.GetBootID()


class GlobalSeq:
  """Manages a global sequence number in a file.

  flock is used to ensure atomicity.

  Args:
    path: Path to the sequence number file (defaults to SEQUENCE_PATH).
    _after_read: A function to call immediately after reading the
        sequence number (for testing).
  """

  def __init__(self, path=None, _after_read=lambda: True):
    path = path or os.path.join(SEQUENCE_PATH)

    self.path = path
    self._after_read = _after_read

    self._Create()

  def _Create(self):
    """Creates the file if it does not yet exist or is invalid."""
    # Need to use os.open, because Python's open does not support
    # O_RDWR | O_CREAT.
    file_utils.TryMakeDirs(os.path.dirname(self.path))
    fd = os.open(self.path, os.O_RDWR | os.O_CREAT)
    with os.fdopen(fd, "r+") as f:
      FileLock(fd, True)
      contents = f.read()
      if contents:
        try:
          _unused_value = int(contents)
          return  # It's all good
        except ValueError:
          logging.exception(
              "Sequence number file %s contains non-integer %r",
              self.path, contents)

      value = self._FindNextSequenceNumber()
      f.write(str(value))
      f.flush()
      os.fsync(fd)

    logging.info("Created global sequence file %s with sequence number %d",
                 self.path, value)

  def _NextOrRaise(self):
    """Returns the next sequence number, raising an exception on failure."""
    with open(self.path, "r+") as f:
      # The file will be closed, and the lock freed, as soon as this
      # block goes out of scope.
      FileLock(f.fileno(), True)
      # Now the FD will be closed/unlocked as soon as we go out of
      # scope.
      value = int(f.read())
      self._after_read()
      f.seek(0)
      f.write(str(value + 1))
      return value

  def Next(self):
    """Returns the next sequence number."""
    try:
      return self._NextOrRaise()
    except (IOError, OSError, ValueError):
      logging.exception("Unable to read global sequence number from %s; "
                        "trying to re-create", self.path)

    # This should really never happen (unless, say, some process
    # corrupts or deletes the file).  Try our best to re-create it;
    # this is not completely safe but better than totally hosing the
    # machine.  On failure, we're really screwed, so just propagate
    # any exception.
    file_utils.TryUnlink(self.path)
    self._Create()
    return self._NextOrRaise()

  def _FindNextSequenceNumber(self):
    """Finds the next sequence number based on the event log file.

    This is the current maximum sequence number (or 0 if none is found)
    plus SEQ_INCREMENT_ON_BOOT.  We do not perform YAML parsing on the
    file; rather we just literally look for a line of the format SEQ_RE.

    A possible optimization would be to only look only in the last (say)
    100KB of the events file.

    Args:
      path: The path to examine (defaults to EVENTS_PATH).
    """
    if not os.path.exists(EVENTS_PATH):
      # There is no events file.  It's safe to start at 0.
      return 0

    try:
      max_seq = 0

      for l in file_utils.ReadLines(EVENTS_PATH):
        # Optimization to avoid needing to evaluate the regexp for each line
        if not l.startswith("SEQ"):
          continue
        match = SEQ_RE.match(l)
        if match:
          max_seq = max(max_seq, int(match.group(1)))

      return max_seq + SEQ_INCREMENT_ON_BOOT + 1
    except Exception:
      # This should really never happen; maybe the events file is
      # so corrupted that a read operation is failing.
      logging.exception("Unable to find next sequence number from "
                        "events file; using system time in ms")
      return int(time.time() * 1000)


class EventLog:
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

    path = os.environ.get("CROS_FACTORY_TEST_PATH", "autotest")
    test_uuid = (os.environ.get("CROS_FACTORY_TEST_INVOCATION") or
                 time_utils.TimedUUID())
    return EventLog(path, test_uuid)

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
          look the same).  If string does not match PREFIX_RE, raises
          ValueError.
      log_id: A UUID for the log (or None, in which case TimedUUID() is used)
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
    self.log_id = log_id or time_utils.TimedUUID()
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

    def get_toolkit_version():
      try:
        return session.GetToolkitVersion()
      except IOError:
        return None  # Ignore IOError for unittests.

    parent_dir = os.path.dirname(EVENTS_PATH)
    if not os.path.exists(parent_dir):
      try:
        os.makedirs(parent_dir)
      except Exception:
        # Maybe someone else tried to create it simultaneously
        if not os.path.exists(parent_dir):
          raise

    if self.opened:
      return
    self.opened = True

    logging.info("Logging events for %s into %s", self.prefix, EVENTS_PATH)

    self.file = open(EVENTS_PATH, "a", encoding='utf-8')
    self._LogUnlocked("preamble",
                      boot_id=GetBootId(),
                      device_id=session.GetDeviceID(),
                      reimage_id=GetReimageId(),
                      boot_sequence=GetBootSequence(),
                      toolkit_version=get_toolkit_version())

  def _LogUnlocked(self, event_name, **kwargs):
    """Same as Log, but requires that the lock has already been acquired.

    See Log() for Args and Returns.
    """
    self._OpenUnlocked()

    if self.file is None:
      raise IOError("cannot append to closed file for prefix %r" % self.prefix)
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
        "TIME": time_utils.TimeString(),
        "LOG_ID": self.log_id,
        "PREFIX": self.prefix,
    }
    data.update(kwargs)
    yaml_data = YamlDump(data) + SYNC_MARKER + "---\n"
    FileLock(self.file.fileno(), True)
    try:
      self.file.write(yaml_data)
      self.file.flush()
    finally:
      FileLock(self.file.fileno(), False)
    os.fsync(self.file.fileno())
