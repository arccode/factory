#!/usr/bin/env python2
# pylint: disable=protected-access
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.rules import privacy


class PrivacyTest(unittest.TestCase):

  def testList(self):
    self.assertEquals(
        ['element1', {u'gbind_attribute': '<redacted 1 chars>'}],
        privacy.FilterDict(['element1', {u'gbind_attribute': '1'}]))

  def testFilterDict(self):
    self.assertEquals(
        dict(a='A', b='B',
             ubind_attribute='<redacted 1 chars>',
             gbind_attribute='<redacted 2 chars>'),
        privacy.FilterDict(
            dict(a='A', b='B', ubind_attribute='U', gbind_attribute=u'GG')))

  def testFilterDictType(self):
    self.assertEquals(
        dict(a='A', b='B',
             ubind_attribute='<redacted type int>',
             gbind_attribute='<redacted 2 chars>'),
        privacy.FilterDict(
            dict(a='A', b='B', ubind_attribute=1, gbind_attribute='GG')))

  def testFilterDictRecursive(self):
    data = dict(gbind_attribute='1',
                test_attribute=dict(ubind_attribute='2'),
                test_attribute_2=[dict(ubind_attribute='3'), 'hi'])
    filtered_data = privacy.FilterDict(data)
    golden_data = dict(
        gbind_attribute='<redacted 1 chars>',
        test_attribute=dict(ubind_attribute='<redacted 1 chars>'),
        test_attribute_2=[dict(ubind_attribute='<redacted 1 chars>'), 'hi'])
    self.assertEquals(filtered_data, golden_data)
    self.assertEquals(
        data,
        dict(
            gbind_attribute='1', test_attribute=dict(ubind_attribute='2'),
            test_attribute_2=[dict(ubind_attribute='3'), 'hi']))

if __name__ == '__main__':
  unittest.main()
