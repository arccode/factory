# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility to get test invocation information."""


import os

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths


# Environment variable names.
ENV_TEST_PATH = 'CROS_FACTORY_TEST_PATH'
ENV_TEST_INVOCATION = 'CROS_FACTORY_TEST_INVOCATION'
ENV_TEST_METADATA = 'CROS_FACTORY_TEST_METADATA'


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
