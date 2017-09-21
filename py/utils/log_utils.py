# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for logging."""

import logging
import os
import sys


_inited_logging = False


def InitLogging(prefix=None, verbose=False):
  """Initializes logging.

  Args:
    prefix: A prefix to display for each log line, e.g., the program name.
    verbose: True for debug logging, false for info logging.
  """
  global _inited_logging  # pylint: disable=global-statement
  assert not _inited_logging, 'May only call log_utils.InitLogging one time.'
  _inited_logging = True

  if not prefix:
    prefix = os.path.basename(sys.argv[0])

  # Make sure that nothing else has initialized logging yet (e.g.,
  # autotest, whose logging_config does basicConfig).
  assert not logging.getLogger().handlers, (
      'Logging has already been initialized')

  level = logging.DEBUG if verbose else logging.INFO
  logging.basicConfig(
      format=('[%(levelname)s] ' + prefix +
              ' %(filename)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=level,
      datefmt='%Y-%m-%d %H:%M:%S')

  logging.debug('Logging initialized.')
