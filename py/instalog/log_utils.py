# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Log-related utilities."""

from __future__ import print_function


LOG_FORMAT = '%(asctime)s [%(levelname)s] [%(name)s] %(message)s'


class LoggerMixin(object):
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
