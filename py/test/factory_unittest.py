#!/usr/bin/python -u
#
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for factory.py."""


import factory_common  # pylint: disable=unused-import

import os
import unittest

from cros.factory.test import factory
from cros.factory.test.test_lists import test_lists


SRCROOT = os.environ.get('CROS_WORKON_SRCROOT')


class FactoryModuleTest(unittest.TestCase):
  """Unittest for Factory module."""

  # TODO(stimim): test FactoryTestList

  def test_py_test_name_to_id(self):
    for name, test_id in (('a', 'A'),
                          ('_', '_'),
                          ('ab', 'Ab'),
                          ('a_b', 'AB'),
                          ('foo_bar', 'FooBar')):
      self.assertEqual(test_id, factory.FactoryTest.pytest_name_to_id(name))


class FactoryTestListTest(unittest.TestCase):

  def testGetNextSibling(self):
    test_list = test_lists.BuildTestListFromString(
        """
    with test_lists.FactoryTest(id='G'):
      with test_lists.FactoryTest(id='G'):
        test_lists.FactoryTest(id='a', pytest_name='t_GGa')
        test_lists.FactoryTest(id='b', pytest_name='t_GGa')
      test_lists.FactoryTest(id='b', pytest_name='t_Gb')
        """, '')
    test = test_list.lookup_path('G.G')
    self.assertEqual(test.get_next_sibling(), test_list.lookup_path('G.b'))
    test = test_list.lookup_path('G.G.a')
    self.assertEqual(test.get_next_sibling(), test_list.lookup_path('G.G.b'))
    test = test_list.lookup_path('G.G.b')
    self.assertIsNone(test.get_next_sibling())


if __name__ == '__main__':
  factory.init_logging('factory_unittest')
  unittest.main()
