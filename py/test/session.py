# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for test session and invocation.

Test harness (usually Goofy in current implementation) should follow the
convention here to invoke a test.
"""

import logging
import os
import subprocess
import threading
from uuid import uuid4

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.utils import file_utils
from cros.factory.utils import log_utils
from cros.factory.utils import type_utils


# Environment variable names.
ENV_TEST_PATH = 'CROS_FACTORY_TEST_PATH'
ENV_TEST_INVOCATION = 'CROS_FACTORY_TEST_INVOCATION'
ENV_TEST_METADATA = 'CROS_FACTORY_TEST_METADATA'

LOG_ROOT = paths.DATA_LOG_DIR

DEVICE_ID_PATH = os.path.join(paths.DATA_DIR, '.device_id')
"""File containing a stable 'Device identifier'.

The file should be located somewhere less likely to be deleted.
The content should be the same even if system image is re-installed.
"""

INSTALLATION_ID_PATH = os.path.join(LOG_ROOT, 'installation_id')
"""File containing a GUID as identifier for software (image) installation.

The file should be deleted when the system software is re-installed,
and the content should be different when re-generated.
"""

INIT_COUNT_PATH = os.path.join(LOG_ROOT, 'init_count')
"""File containing the number of times session (Goofy) has been initialized."""

# TODO(hungte) Add a better cache decorator for cache-able values.
# Cache the DEVICE_ID and INSTALLATION_ID after being read from disk or
# after being generated (if they do not yet exist).
_device_id = None
_installation_id = None

_session_lock = threading.Lock()


console = type_utils.LazyObject(
    log_utils.FileLogger, 'console', paths.CONSOLE_LOG_PATH,
    os.environ.get(ENV_TEST_PATH))
"""A wrapper for sending messages to global (UI) console using logging API."""


def GetDeviceID():
  """Returns the device ID.

  The device ID is created and stored by init/goofy.d/device/device_id.sh on
  system startup. Read and cache it in the global variable _device_id.
  """
  with _session_lock:
    global _device_id  # pylint: disable=global-statement
    if _device_id is None:
      if os.path.exists(DEVICE_ID_PATH):
        _device_id = file_utils.ReadFile(DEVICE_ID_PATH).strip()
      else:
        # The device_id file doesn't exist, we probably are not on DUT, just
        # run bin/device_id once and return the result.
        device_id_bin = os.path.join(paths.FACTORY_DIR, 'bin', 'device_id')
        _device_id = subprocess.check_output(device_id_bin).strip()
    return _device_id


def GetInstallationID():
  """Returns the installation ID.

  This is stored in INSTALLATION_ID_PATH; one is generated if not available.
  """
  with _session_lock:
    global _installation_id  # pylint: disable=global-statement
    if not _installation_id:
      if os.path.exists(INSTALLATION_ID_PATH):
        _installation_id = file_utils.ReadFile(INSTALLATION_ID_PATH).strip()
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
  """Returns the current session init count (or -1 if not available)."""
  # TODO(itspeter): Remove the path argument once event_log.py is phased out.
  try:
    return int(file_utils.ReadFile(path))
  except (IOError, ValueError):
    return -1


def IncrementInitCount(path=INIT_COUNT_PATH):
  """Increments the session init count.

  Creates the init count file if it does not already exist.
  """
  # TODO(itspeter): Remove the path argument once event_log.py is phased out.
  init_count = GetInitCount(path) + 1

  logging.info('Session (Goofy) init count = %d', init_count)

  file_utils.TryMakeDirs(os.path.dirname(path))
  with open(path, 'w') as f:
    f.write('%d' % init_count)
    f.flush()
    os.fsync(f.fileno())


def GetBootID():
  """Returns the boot ID."""
  return file_utils.ReadFile('/proc/sys/kernel/random/boot_id').strip()


def GetToolkitVersion():
  """Returns TOOLKIT_VERSION of the factory directory."""
  return file_utils.ReadFile(paths.FACTORY_TOOLKIT_VERSION_PATH).rstrip()


def GetCurrentTestPath():
  """Returns the path of the currently executing test, if any."""
  return os.environ.get(ENV_TEST_PATH)


def GetCurrentTestInvocation():
  """Returns the invocation UUID of current running test, if any."""
  return os.environ.get(ENV_TEST_INVOCATION)


def GetVerboseTestLogPath():
  """Returns a path for verbose logging of current test.

  The 'verbose test log' is a special log file that will be kept in log
  directory, and not merged into ``factory.log`` or ``testlog``.
  It was introduced to reduce log size sent to factory servers - helpful for
  debugging locally, but not meant for being stored if nothing goes wrong.

  The file name will contain test invocation ID and thus this method
  can only be called from a test.
  """
  log_name = '%s-log-%s' % (GetCurrentTestPath(), GetCurrentTestInvocation())
  return os.path.join(paths.DATA_LOG_DIR, log_name)
