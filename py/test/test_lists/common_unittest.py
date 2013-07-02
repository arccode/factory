#!/usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import unittest


import factory_common  # pylint: disable=W0611
from cros.factory.test.test_lists.common import (
    BuildTestLists,
    FactoryTest,
    TestGroup,
    TestList,
    TestListError)


class CommonTest(unittest.TestCase):
  def testBasic(self):
    class FakeModule(object):
      @staticmethod
      def CreateTestLists():
        with TestList('main', 'Main'):
          FactoryTest(id='f1', pytest_name='F1')
          with TestGroup(id='g'):
            FactoryTest(id='f2', pytest_name='F2')
        with TestList('alternate', 'Alternate'):
          FactoryTest(id='f3', pytest_name='F3')

    test_lists = BuildTestLists(FakeModule)
    self.assertItemsEqual(['alternate', 'main'], test_lists.keys())

    subtests = test_lists['main'].subtests
    self.assertEqual('f1', subtests[0].id)
    self.assertEqual('g', subtests[1].id)
    self.assertEqual('f2', subtests[1].subtests[0].id)

    self.assertEqual('f3', test_lists['alternate'].subtests[0].id)

  def testNotWithinTestList(self):
    class FakeModule(object):
      @staticmethod
      def CreateTestLists():
        FactoryTest(id='x')

    self.assertRaisesRegexp(
        TestListError, 'not within a test list', BuildTestLists, FakeModule)

  def testDuplicateTestList(self):
    class FakeModule(object):
      @staticmethod
      def CreateTestLists():
        for _ in range(2):
          with TestList('a', 'A'):
            pass

    self.assertRaisesRegexp(
        TestListError, 'Duplicate test list', BuildTestLists, FakeModule)

  def testNestedTestList(self):
    class FakeModule(object):
      @staticmethod
      def CreateTestLists():
        with TestList('a', 'A'):
          with TestList('b', 'B'):
            pass

    self.assertRaisesRegexp(
        TestListError, 'within another test list', BuildTestLists, FakeModule)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
