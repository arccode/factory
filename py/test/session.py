# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for test session and invocation.

Test harness (usually Goofy in current implementation) should follow the
convention here to invoke a test.
"""

import logging
import os
import uuid

from cros.factory.test.env import paths
from cros.factory.utils import file_utils
from cros.factory.utils import log_utils
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils


# Environment variable names.
ENV_TEST_PATH = 'CROS_FACTORY_TEST_PATH'
ENV_TEST_INVOCATION = 'CROS_FACTORY_TEST_INVOCATION'
ENV_TEST_METADATA = 'CROS_FACTORY_TEST_METADATA'
ENV_TEST_FILE_PATH = 'CROS_FACTORY_TEST_FILE_PATH'

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


console = type_utils.LazyObject(
    log_utils.FileLogger, 'console', paths.CONSOLE_LOG_PATH,
    os.environ.get(ENV_TEST_PATH))
"""A wrapper for sending messages to global (UI) console using logging API."""


@type_utils.CachedGetter
def GetDeviceID():
  """Returns the device ID.

  The device ID is created and stored by init/goofy.d/device/device_id.sh
  calling bin/device_id on system startup.
  """
  if os.path.exists(DEVICE_ID_PATH):
    return file_utils.ReadFile(DEVICE_ID_PATH).strip()
  # The device_id file doesn't exist, we probably are not on DUT, just
  # run bin/device_id once and return the result.
  device_id_bin = os.path.join(paths.FACTORY_DIR, 'bin', 'device_id')
  return process_utils.CheckOutput(device_id_bin).strip()


@type_utils.CachedGetter
def GetInstallationID():
  """Returns the installation ID.

  This is stored in INSTALLATION_ID_PATH; one is generated if not available.
  """
  value = None
  if os.path.exists(INSTALLATION_ID_PATH):
    value = file_utils.ReadFile(INSTALLATION_ID_PATH).strip()
  if not value:
    value = str(uuid.uuid4())
    file_utils.TryMakeDirs(os.path.dirname(INSTALLATION_ID_PATH))
    # There may be race condition here, but that is unlikely to happen due to
    # how we use GetInstallationID today.
    with file_utils.AtomicWrite(INSTALLATION_ID_PATH) as f:
      f.write(value)
    logging.info('No installation_id available yet: generated %s', value)
  return value


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
  with file_utils.AtomicWrite(path) as f:
    f.write('%d' % init_count)


@type_utils.CachedGetter
def GetBootID():
  """Returns the boot ID."""
  return file_utils.ReadFile('/proc/sys/kernel/random/boot_id').strip()


def GetToolkitVersion():
  """Returns TOOLKIT_VERSION of the factory directory."""
  return file_utils.ReadFile(paths.FACTORY_TOOLKIT_VERSION_PATH).rstrip()


@type_utils.CachedGetter
def GetCurrentTestPath():
  """Returns the path of the currently executing test, if any.

  This function may be cached because each invocation process should not have
  test path changed during execution.
  """
  return os.environ.get(ENV_TEST_PATH)


@type_utils.CachedGetter
def GetCurrentTestInvocation():
  """Returns the invocation UUID of current running test, if any.

  This function may be cached because each invocation process should not have
  test invocation changed during execution.
  """
  return os.environ.get(ENV_TEST_INVOCATION)


@type_utils.CachedGetter
def GetCurrentTestFilePath():
  """Returns the file path of the currently executing test, if any.

  This function may be cached because each invocation process should not have
  test file changed during execution.
  """
  return os.environ.get(ENV_TEST_FILE_PATH)


@type_utils.CachedGetter
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
