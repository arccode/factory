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


class EventLogException(Exception):
  pass


# Since gooftool uses this.
TimeString = utils.TimeString


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
  """Wrap yaml.dump to make calling convention consistent."""
  return yaml.dump(structured_data,
                   default_flow_style=False,
                   allow_unicode=True)


# TODO(tammo): Replace these definitions references to real canonical
# data, once the corresponding modules move over from the autotest
# repo.

EVENT_LOG_DIR = os.path.join(factory.get_state_root(), "events")

# Path to use to generate a device ID in case none exists (i.e.,
# there is no wlan0 interface).
DEVICE_ID_PATH = os.path.join(EVENT_LOG_DIR, ".device_id")

# Path to use to generate an image ID in case none exists (i.e.,
# this is the first time we're creating an event log).
IMAGE_ID_PATH = os.path.join(EVENT_LOG_DIR, ".image_id")

BOOT_SEQUENCE_PATH = os.path.join(EVENT_LOG_DIR, ".boot_sequence")

WLAN0_MAC_PATH = "/sys/class/net/wlan0/address"

PREFIX_RE = re.compile("^[a-zA-Z0-9_\.]+$")
EVENT_NAME_RE = re.compile(r"^[a-zA-Z_]\w*$")
EVENT_KEY_RE = EVENT_NAME_RE

device_id = None
image_id = None


def GetDeviceId():
  """Returns the device ID.

  This is derived from the wlan0 MAC address.  If no wlan0 device is
  available, one is generated into DEVICE_ID_PATH.
  """
  global device_id  # pylint: disable=W0603
  if not device_id:
    for path in [WLAN0_MAC_PATH, DEVICE_ID_PATH]:
      if os.path.exists(path):
        device_id = open(path).read().strip()
        break
    else:
      device_id = str(uuid4())
      utils.TryMakeDirs(os.path.dirname(DEVICE_ID_PATH))
      with open(DEVICE_ID_PATH, "w") as f:
        print >> f, device_id
      logging.warning('No device ID available: generated %s', device_id)
  return device_id


def GetBootId():
  """Returns the boot ID."""
  return open("/proc/sys/kernel/random/boot_id", "r").read().strip()


def GetImageId():
  """Returns the image ID.

  This is stored in IMAGE_ID_PATH; one is generated if not available.
  """
  global image_id  # pylint: disable=W0603
  if not image_id:
    if os.path.exists(IMAGE_ID_PATH):
      image_id = open(IMAGE_ID_PATH).read().strip()
    if not image_id:
      image_id = str(uuid4())
      utils.TryMakeDirs(os.path.dirname(IMAGE_ID_PATH))
      with open(IMAGE_ID_PATH, "w") as f:
        print >> f, image_id
      logging.info('No image ID available yet: generated %s', image_id)
  return image_id


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
    os.fdatasync(f.fileno())


class GlobalSeq(object):
  '''Manages a global sequence number in a file.

  We keep two files, '.seq' and '.seq.backup'.  Each file contains the
  next number to be assigned (or an empty file for '0').  If all else
  fails, the current time in ms is used.

  flock is used to ensure atomicity.
  '''
  BACKUP_SEQUENCE_INCREMENT = 100
  BACKUP_SUFFIX = '.backup'

  def __init__(self, path=None, _after_read=lambda: True):
    path = path or os.path.join(EVENT_LOG_DIR, '.seq')

    self.path = path
    self.backup_path = path + self.BACKUP_SUFFIX
    # Time module; may be mocked
    self._time = time
    # Function to call immediately after reading the value;
    # may be used for testing atomicity.
    self._after_read = _after_read

    for f in [self.path, self.backup_path]:
      try:
        # Try to create the file atomically.
        utils.TryMakeDirs(os.path.dirname(f))
        fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        logging.info('Created global sequence file %s', f)
        os.close(fd)
      except OSError:
        if not os.path.exists(path):
          raise

  def Next(self):
    try:
      fd = os.open(self.path, os.O_RDWR)
      try:
        fcntl.flock(fd, fcntl.LOCK_EX)
      except:
        # flock failed; close the file and re-raise.
        os.close(fd)
        raise

      with os.fdopen(fd, 'r+') as f:
        value = int(f.read() or '0')
        self._after_read()
        f.seek(0)
        f.write(str(value + 1))

      # Also write to the backup file.
      with open(self.backup_path, 'w') as f:
        f.write(str(value + 1))

      return value
    except (IOError, OSError, ValueError):
      logging.exception('Unable to read global sequence number from %s; '
                        'trying backup %s', self.path, self.backup_path)

      try:
        with open(self.backup_path) as f:
          value = int(f.read() or '0') + self.BACKUP_SEQUENCE_INCREMENT
      except (IOError, OSError, ValueError):
        # Oy, couldn't even read that!  Fall back to system time in ms.
        value = int(self._time.time() * 1000)
        logging.exception('Unable to read backup sequence number.  Using '
                          'system time in milliseconds (%d)', value)

      # Save the value and backup value.
      with open(self.path, 'w') as f:
        f.write(str(value + 1))
      with open(self.backup_path, 'w') as f:
        f.write(str(value + 1))

      return value


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
    """Creates an EventLog object for the running autotest."""
    path = os.environ.get('CROS_FACTORY_TEST_PATH', 'autotest')
    uuid = os.environ.get('CROS_FACTORY_TEST_INVOCATION') or TimedUuid()
    return EventLog(path, uuid)

  def __init__(self, prefix, log_id=None, defer=True, seq=None, suppress=False):
    """Creates a new event log file, returning an EventLog instance.

    A new file will be created of the form <prefix>-UUID, where UUID is
    randomly generated.  The file will be initialized with a preamble
    that includes the following fields:
      device_id - Unique per device (eg, MAC addr).
      image_id - Unique each time device is imaged.

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
      raise ValueError, "prefix %r must match re %s" % (
        prefix, PREFIX_RE.pattern)
    self.prefix = prefix
    self.lock = threading.Lock()
    self.seq = seq or GlobalSeq()
    self.log_id = log_id or TimedUuid()
    self.filename = "%s-%s" % (prefix, self.log_id)
    self.path = os.path.join(EVENT_LOG_DIR, self.filename)
    if os.path.exists(self.path):
      raise EventLogException, "Log %s already exists" % self.path
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
      EVENT - From event_name input.
      ... - Other fields from kwargs.

    Stanzas are terminated by "---\n".

    event_name and kwarg keys must all start with [a-zA-Z_] and
    contain only [a-zA-Z0-9_] (like Python identifiers).

    Args:
      event_name: Used to indentify event field.
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
    parent_dir = os.path.dirname(self.path)
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

    logging.info('Logging events for %s to %s', self.prefix, self.path)

    self.file = open(self.path, "w")
    self._LogUnlocked("preamble",
                      log_id=self.log_id,
                      boot_id=GetBootId(),
                      device_id=GetDeviceId(),
                      image_id=GetImageId(),
                      boot_sequence=GetBootSequence(),
                      factory_md5sum=factory.get_current_md5sum(),
                      filename=self.filename)

  def _LogUnlocked(self, event_name, **kwargs):
    """Same as Log, but requires that the lock has already been acquired.

    See Log() for Args and Returns.
    """
    self._OpenUnlocked()

    if self.file is None:
      raise IOError, "cannot append to closed file for prefix %r" % (
        self.prefix)
    if not EVENT_NAME_RE.match(event_name):
      raise ValueError, "event_name %r must match %s" % (
        event_name, EVENT_NAME_RE.pattern)
    for k in kwargs:
      if not EVENT_KEY_RE.match(k):
        raise ValueError, "key %r must match re %s" % (
          k, EVENT_KEY_RE.pattern)
    data = {
        "EVENT": event_name,
        "SEQ": self.seq.Next(),
        "TIME": utils.TimeString()
        }
    data.update(kwargs)
    self.file.write(YamlDump(data))
    self.file.write("---\n")
    self.file.flush()
    os.fdatasync(self.file.fileno())
