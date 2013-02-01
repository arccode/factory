#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils import test_utils


class TestUtilsUnittest(unittest.TestCase):
  def testStubOutAttributes(self):
    class Obj(object):
      a = 'A'
      b = 'B'

    obj = Obj()
    with test_utils.StubOutAttributes(obj, a='A2', c='C'):
      self.assertEquals('A2', obj.a)
      self.assertEquals('B', obj.b)
      self.assertEquals('C', obj.c)

    self.assertEquals('A', obj.a)
    self.assertEquals('B', obj.b)
    self.assertRaises(AttributeError, lambda: obj.c)


if __name__ == '__main__':
  unittest.main()
