# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for logging."""

import logging
import os
import sys

from . import file_utils


DEFAULT_LOG_FORMAT = '[%(levelname)s] %(message)s'

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


def FileLogger(logger, log_path, log_prefix=None, log_format=None, level=None):
  """Creates a logger storing logs in file.

  On creation, the folder of log file will be created, and the log file will be
  opened in append mode.

  If you need to delay the creation of logger (for example, having the logger
  created in module import stage), wrap this function with
  ``type_utils.LazyObject``.

  Args:
    logger: A string as name of logger, for example 'console'.
    log_path: A string for path to output file.
    log_prefix: If specified, prefix this in all log messages with colon.
    log_format: A format string to override DEFAULT_LOG_FORMAT.
    level: An integer for controlling verbosity (as logging.level).

  Returns:
    A logger instance (see `logging` module for more information).
  """

  if log_format is None:
    log_format = DEFAULT_LOG_FORMAT
  if log_prefix:
    log_format = log_prefix + ': ' + log_format
  if level is None:
    level = logging.INFO

  file_utils.TryMakeDirs(os.path.dirname(log_path))
  handler = logging.FileHandler(log_path, 'a')
  handler.setFormatter(logging.Formatter(log_format))
  ret = logging.getLogger(logger)
  ret.addHandler(handler)
  ret.setLevel(level)
  return ret
