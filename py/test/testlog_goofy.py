# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Goofy specific function for logging."""

import logging
import os
import threading
from uuid import uuid4

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.utils import file_utils


LOG_ROOT = paths.GetLogRoot()

# The location to store the device ID file should be a place that is
# less likely to be deleted.
DEVICE_ID_PATH = os.path.join(LOG_ROOT, 'device_id')

WLAN0_MAC_PATH = '/sys/class/net/wlan0/address'
MLAN0_MAC_PATH = '/sys/class/net/mlan0/address'
# TODO(kitching): Add CPUID for Intel devices?
DEVICE_ID_SEARCH_PATHS = [WLAN0_MAC_PATH, MLAN0_MAC_PATH]

# Path to use to generate an image ID in case none exists (i.e.,
# this is the first time we're creating an event log).
INSTALLATION_ID_PATH = os.path.join(LOG_ROOT, 'installation_id')

# itspeter
# File containing the number of times Goofy has been initialized.
INIT_COUNT_PATH = os.path.join(LOG_ROOT, 'init_count')

# The /var/factory/log directory (or equivalent if in the chroot).
LOG_DIR = paths.GetLogRoot()

# Cache the DEVICE_ID and INSTALLATION_ID after being read from disk or
# after being generated (if they do not yet exist).
_device_id = None
_installation_id = None

_testlog_goofy_lock = threading.Lock()

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
  with _testlog_goofy_lock:
    global _device_id  # pylint: disable=global-statement
    if _device_id:
      return _device_id

    # Always respect the device ID recorded in DEVICE_ID_PATH first.
    if os.path.exists(DEVICE_ID_PATH):
      _device_id = open(DEVICE_ID_PATH).read().strip()
      if _device_id:
        return _device_id

    # Find or generate device ID from the search path.
    for p in DEVICE_ID_SEARCH_PATHS:
      if os.path.exists(p):
        _device_id = open(p).read().strip()
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


def GetInstallationID():
  """Returns the installation ID.

  This is stored in INSTALLATION_ID_PATH; one is generated if not available.
  """
  with _testlog_goofy_lock:
    global _installation_id  # pylint: disable=global-statement
    if not _installation_id:
      if os.path.exists(INSTALLATION_ID_PATH):
        _installation_id = open(INSTALLATION_ID_PATH).read().strip()
      if not _installation_id:
        _installation_id = str(uuid4())
        logging.info('No installation_id available yet: generated %s',
                     _installation_id)

        # Save the installation ID to INSTALLATION_ID_PATH for future reloading.
        file_utils.TryMakeDirs(os.path.dirname(INSTALLATION_ID_PATH))
        with open(INSTALLATION_ID_PATH, 'w') as f:
          f.write(_installation_id)
          f.flush()
          os.fsync(f)
    return _installation_id


def GetInitCount(path=INIT_COUNT_PATH):
  """Returns the current Goofy init count (or -1 if not available)."""
  # TODO(itspeter): Remove the path argument once event_log.py is phased out.
  try:
    return int(open(path).read())
  except (IOError, ValueError):
    return -1


def IncrementInitCount(path=INIT_COUNT_PATH):
  """Increments the Goofy init count.

  Creates the init count file if it does not already exist.
  """
  # TODO(itspeter): Remove the path argument once event_log.py is phased out.
  init_count = GetInitCount(path) + 1

  logging.info('Goofy init count = %d', init_count)

  file_utils.TryMakeDirs(os.path.dirname(path))
  with open(path, 'w') as f:
    f.write('%d' % init_count)
    f.flush()
    os.fsync(f.fileno())


def GetBootID():
  """Returns the boot ID."""
  return open('/proc/sys/kernel/random/boot_id', 'r').read().strip()
