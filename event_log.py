# -*- coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Routines for producing event logs."""


import logging
import re
import os
import threading
import time
import yaml

from uuid import uuid4

import factory_common
from autotest_lib.client.cros import factory


class EventLogException(Exception):
  pass


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


def TimeString(unix_time=None):
  """Returns the current time (using UTC) as a string.

  The format is like ISO8601 but with milliseconds:

    2012-05-22T14:15:08.123Z
  """

  t = unix_time or time.time()
  return "%s.%03dZ" % (time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)),
                    int((t - int(t)) * 1000))

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

WLAN0_MAC_PATH = "/sys/class/net/wlan0/address"

PREFIX_RE = re.compile("^[a-zA-Z0-9_\.]+$")
EVENT_NAME_RE = re.compile("^[a-z0-9_]+$")
EVENT_KEY_RE = EVENT_NAME_RE

device_id = None
image_id = None


def GetDeviceId():
  """Returns the device ID.

  This is derived from the wlan0 MAC address.  If no wlan0 device is
  available, one is generated into DEVICE_ID_PATH.
  """
  global device_id
  if not device_id:
    for path in [WLAN0_MAC_PATH, DEVICE_ID_PATH]:
      if os.path.exists(path):
        device_id = open(path).read().strip()
        break
    else:
      device_id = str(uuid4())
      with open(DEVICE_ID_PATH, "w") as f:
        print >>f, device_id
      logging.warning('No device ID available: generated %s', device_id)
  return device_id


def GetBootId():
  """Returns the boot ID."""
  return open("/proc/sys/kernel/random/boot_id", "r").read().strip()


def GetImageId():
  """Returns the image ID.

  This is stored in IMAGE_ID_PATH; one is generated if not available.
  """
  global image_id
  if not image_id:
    if os.path.exists(IMAGE_ID_PATH):
      image_id = open(IMAGE_ID_PATH).read().strip()
    else:
      image_id = str(uuid4())
      with open(IMAGE_ID_PATH, "w") as f:
        print >>f, image_id
      logging.info('No image ID available yet: generated %s', image_id)
  return image_id


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

  def __init__(self, prefix, log_id=None):
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
    """
    if not PREFIX_RE.match(prefix):
      raise ValueError, "prefix %r must match re %s" % (
        prefix, PREFIX_RE.pattern)
    self.prefix = prefix
    self.seq = 0
    self.lock = threading.Lock()
    self.log_id = log_id or TimedUuid()
    filename = "%s-%s" % (prefix, self.log_id)
    if not os.path.exists(EVENT_LOG_DIR):
      try:
        os.makedirs(EVENT_LOG_DIR)
      except:
        # Maybe someone else tried to create it simultaneously
        if not os.path.exists(EVENT_LOG_DIR):
          raise
    self.path = os.path.join(EVENT_LOG_DIR, filename)
    logging.info('Logging events for %s to %s', prefix, self.path)
    if os.path.exists(self.path):
      raise EventLogException, "Log %s already exists" % self.path
    self.file = open(self.path, "w")
    self.Log("preamble",
             log_id=self.log_id,
             boot_id=GetBootId(),
             device_id=GetDeviceId(),
             image_id=GetImageId(),
             filename=filename)

  def Close(self):
    """Closes associated log file."""
    with self.lock:
      self.file.close()
      self.file = None

  def Log(self, event_name, **kwargs):
    """Writes new event stanza to log file, with consistent metadata.

    Appends a stanza contain the following fields to the log:
      TIME: Formatted as per TimeString().
      SEQ: Monotonically increating counter.  The preamble will always
        have SEQ=0.
      EVENT - From event_name input.
      ... - Other fields from kwargs.

    Stanzas are terminated by "---\n".

    Args:
      event_name: Used to indentify event field.  Must be serialized
        data, eg string or int.
      kwargs: Dict of additional fields for inclusion in the event
        stanza.  Field keys must be alphanumeric and lowercase. Field
        values will be automatically yaml-ified.  Other data
        types will result in a ValueError.
    """
    def TypeCheck(data):
      if isinstance(data, dict):
        for k, v in data.items():
          if not isinstance(k, str):
            raise ValueError, "dict keys must be strings, found key %r" % k
          TypeCheck(v)
      elif isinstance (data, list):
        map(TypeCheck, data)

    with self.lock:
      if self.file is None:
        raise IOError, "cannot append to closed file for prefix %r" % (
          self.prefix)
      if not EVENT_NAME_RE.match(event_name):
        raise ValueError, "event_name %r must match %s" % (
          event_name, EVENT_NAME_RE.pattern)
      TypeCheck(kwargs)
      for k in kwargs:
        if not EVENT_KEY_RE.match(k):
          raise ValueError, "key %r must match re %s" % (
            k, EVENT_KEY_RE.pattern)
      data = {
          "EVENT": event_name,
          "SEQ": self.seq,
          "TIME": TimeString()
          }
      data.update(kwargs)
      self.file.write(YamlDump(data))
      self.file.write("---\n")
      self.file.flush()
      self.seq += 1
