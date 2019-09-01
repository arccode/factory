#!/usr/bin/env python2
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for debug_utils.py."""

import logging
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import debug_utils


class CatchExceptionTest(unittest.TestCase):
  """Unittest for CatchException."""

  def testCatchException(self):
    class Foo(object):
      """A class that should suppress its exception in its function."""
      @debug_utils.CatchException('Foo')
      def BadBar(self):
        logging.warning('Bad bar is called.')
        raise Exception('I am bad.')

    f1 = Foo()
    f1.BadBar()

  def testCatchExceptionDisable(self):
    class Foo(object):
      """A class that should suppress its exception in its function."""
      @debug_utils.CatchException('Foo', False)
      def BadBar(self):
        logging.warning('Bad bar is called.')
        raise Exception('I am bad.')

    f1 = Foo()
    with self.assertRaises(Exception):
      f1.BadBar()


class GetCallerNameTest(unittest.TestCase):
  """Unittest for GetCallerName."""

  def testGetCallerName(self):
    def A():
      self.assertEqual('A', debug_utils.GetCallerName(0))
      self.assertEqual('B', debug_utils.GetCallerName(1))
      self.assertEqual('testGetCallerName', debug_utils.GetCallerName(2))
    def B():
      A()
    B()
    # ValueError: call stack is not deep enough
    with self.assertRaises(ValueError):
      debug_utils.GetCallerName(50)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
