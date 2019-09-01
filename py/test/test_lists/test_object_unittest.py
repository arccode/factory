#!/usr/bin/env python2
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for factory.py."""


import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.test_lists import test_object


SRCROOT = os.environ.get('CROS_WORKON_SRCROOT')


class FactoryTestTest(unittest.TestCase):
  """Unittest for Factory module."""
  def test_py_test_name_to_id(self):
    for name, label in (('a', 'A'),
                        ('a.b', 'A B'),
                        ('test', 'Test'),
                        ('a_long_test_name', 'A Long Test Name')):
      self.assertEqual(label, test_object.FactoryTest.PytestNameToLabel(name))
    for label, test_id in (('A test', 'ATest'),
                           ('ab', 'Ab'),
                           ('a_b', 'AB'),
                           ('foo_bar', 'FooBar')):
      self.assertEqual(test_id, test_object.FactoryTest.LabelToId(label))


if __name__ == '__main__':
  unittest.main()
