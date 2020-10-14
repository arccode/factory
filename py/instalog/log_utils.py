# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Log-related utilities."""

import logging
import multiprocessing


LOG_FORMAT = '%(asctime)s [%(levelname)s] [%(name)s] %(message)s'


class MultiprocessingFileHandler(logging.FileHandler):

  def createLock(self):
    """Overrides the original function, and uses multiprocessing RLock."""
    self.lock = multiprocessing.RLock()


class MultiprocessingStreamHandler(logging.StreamHandler):

  def createLock(self):
    """Overrides the original function, and uses multiprocessing RLock."""
    self.lock = multiprocessing.RLock()


def InitLogging(handlers, log_level=logging.DEBUG):
  """Initializes the logger and sets up the handlers."""
  if isinstance(handlers, logging.Handler):
    handlers = [handlers]
  assert isinstance(handlers, list)
  logger = logging.getLogger()
  logger.setLevel(log_level)
  logger.handlers = handlers


def GetFileHandler(log_file, log_level=logging.INFO):
  """Initializes and returns a file handler."""
  fh = MultiprocessingFileHandler(log_file)
  fh.setFormatter(logging.Formatter(LOG_FORMAT))
  fh.setLevel(log_level)
  return fh


def GetStreamHandler(log_level=logging.INFO):
  """Initializes and returns a stream handler."""
  sh = MultiprocessingStreamHandler()
  sh.setFormatter(logging.Formatter(LOG_FORMAT))
  sh.setLevel(log_level)
  return sh


class LoggerMixin:
  """Adds logger methods to a class via mix-in.

  Assumes that self.logger exists and works like a standard logger.

  Usage (note order of the classes in the inheritance list):

    class MyClass(log_utils.LoggerMixin, MyBaseClass):

      def __init__(self, logger):
        # log_utils.LoggerMixin creates shortcut functions for convenience.
        self.logger = logger
  """

  def debug(self, *arg, **kwargs):
    return self.logger.debug(*arg, **kwargs)

  def info(self, *arg, **kwargs):
    return self.logger.info(*arg, **kwargs)

  def warning(self, *arg, **kwargs):
    return self.logger.warning(*arg, **kwargs)

  def error(self, *arg, **kwargs):
    return self.logger.error(*arg, **kwargs)

  def critical(self, *arg, **kwargs):
    return self.logger.critical(*arg, **kwargs)

  def exception(self, *arg, **kwargs):
    return self.logger.exception(*arg, **kwargs)
