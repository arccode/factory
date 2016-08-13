#!/usr/bin/env python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for debug_utils.py."""

import logging
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils.debug_utils import CatchException


class CatchExceptionTest(unittest.TestCase):
  """Unittest for CatchException."""

  def testCatchException(self):
    class Foo(object):
      """A class that should suppress its exception in its function."""
      @CatchException('Foo')
      def BadBar(self):
        logging.warning('Bad bar is called.')
        raise Exception('I am bad.')

    f1 = Foo()
    f1.BadBar()

  def testCatchExceptionDisable(self):
    class Foo(object):
      """A class that should suppress its exception in its function."""
      @CatchException('Foo', False)
      def BadBar(self):
        logging.warning('Bad bar is called.')
        raise Exception('I am bad.')

    f1 = Foo()
    with self.assertRaises(Exception):
      f1.BadBar()

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
