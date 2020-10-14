#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for log-related utilities."""

import logging
import unittest
from unittest import mock

from cros.factory.instalog import log_utils


class LoggerMixinTest(unittest.TestCase):
  """Tests for the LoggerMixin class."""

  def testMixin(self):
    """Checks that functions in the mix-in correctly call the logger."""

    class WithLoggerAndDebug:

      def __init__(self, logger):
        self.logger = logger

      def debug(self, *args, **kwargs):
        pass

    # This is the incorrect order.  LoggerMixin is the base class, and
    # WithLoggerAndDebug is overriding the debug method.
    class LoggerAndDebugAsBase(WithLoggerAndDebug, log_utils.LoggerMixin):

      pass

    # This is the correct order.  WithLoggerAndDebug is the base class,
    # and LoggerMixin is overriding the debug method.
    class MixinAsBase(log_utils.LoggerMixin, WithLoggerAndDebug):

      pass

    logger = mock.Mock()
    LoggerAndDebugAsBase(logger).debug('test')
    logger.debug.assert_not_called()
    MixinAsBase(logger).debug('test')
    logger.debug.assert_called_with('test')


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO, format=log_utils.LOG_FORMAT)
  unittest.main()
