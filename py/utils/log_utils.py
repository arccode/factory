# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for logging."""

import logging
import os
import sys
import time

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


class NoisyLogger:
  """A processor for handling logs that repeats quickly.

  Most tests implementing retry (or do something periodically) will easily
  produce lots of same messages and we may want them being suppressed if the
  message is not changed.
  """

  def __init__(self, logger, suppress_limit=None, suppress_timeout=None,
               suppress_logger=None, all_suppress_logger=None):
    """Constructor.

    Args:
      logger: A logger function, for example logging.info.
      suppress_limit: An integer for limit of times to suppress, or None to
        suppress until message is changed.
      suppress_timeout: A timeout in seconds, or None to not time out.
      suppress_logger: A logger function to be invoked when first time a message
        is suppressed. None to use default (``_DefaultSuppressLogger``).
      all_suppress_logger: A secondary logger function for suppressed messages,
        for example logging.debug. None to use default
        (``_DefaultAllSuppressLogger``).
    """
    if all_suppress_logger is None:
      all_suppress_logger = self._DefaultAllSuppressLogger
    if suppress_logger is None:
      suppress_logger = self._DefaultSuppressLogger
    self._logger = logger
    self._all_suppress_logger = all_suppress_logger
    self._suppress_limit = suppress_limit
    self._suppress_timeout = suppress_timeout
    self._suppress_logger = suppress_logger
    self._suppress_count = 0
    self._suppress_start = time.time()
    self._last_message = None

  def _DefaultSuppressLogger(self, message, *args, **kargs):
    """The default logger when the message is first time suppressed."""
    del args  # Unused
    del kargs  # Unused
    logging.info('Suppressed repeating message(s): %s', message)

  def _DefaultAllSuppressLogger(self, message, *args, **kargs):
    del args  # Unused
    del kargs  # Unused
    logging.debug('Suppressed repeating message(s): %s', message)

  def ShouldSuppress(self, message):
    """Returns if the new message should be suppressed or not."""
    if message != self._last_message:
      return False
    if (self._suppress_timeout is not None and
        time.time() - self._suppress_start >= self._suppress_timeout):
      return False
    if self._suppress_limit is None:
      return True
    return self._suppress_count < self._suppress_limit

  def Log(self, message, *args, **kargs):
    """Logs the new message.

    Args:
      message: An object to be logged.
      args: Extra arguments sent to logger.
      kargs: Keyword arguments sent to logger.
    """
    if self.ShouldSuppress(message):
      if self._suppress_count == 0:
        self._suppress_logger(message, *args, **kargs)
      self._all_suppress_logger(message, *args, **kargs)
      self._suppress_count += 1
    else:
      self._last_message = message
      self._logger(message, *args, **kargs)
      self._suppress_count = 0
      if self._suppress_timeout is not None:
        self._suppress_start = time.time()
