#!/usr/bin/env python
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Unittest for cros.factory.utils.type_utils."""

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils import type_utils


class FlattenListTest(unittest.TestCase):

  def runTest(self):
    self.assertEquals([], type_utils.FlattenList([]))
    self.assertEquals([], type_utils.FlattenList([[]]))
    self.assertEquals([1], type_utils.FlattenList([1]))
    self.assertEquals([1], type_utils.FlattenList([1, []]))
    self.assertEquals([1, 2, 3, 4, 5, 6],
                      type_utils.FlattenList([1, 2, [3, 4, []], 5, 6]))


class AttrDictTest(unittest.TestCase):

  def testAttrDictInit(self):
    init_value = {
        'key': 'value_1',
        'keydict': {'key2': 'value_key2_2'},
        'keylist': [0, 1, 2, {'key3': 'value_keylist_3_key3'}, 4]}
    adict = type_utils.AttrDict(init_value)
    self.assertEqual('value_1', adict.key)
    self.assertEqual('value_key2_2', adict.keydict.key2)
    self.assertEqual('value_keylist_3_key3', adict.keylist[3].key3)

  def testAttrDictSetGet(self):
    adict = type_utils.AttrDict()
    adict['foo'] = 'bar'
    self.assertEqual('bar', adict.foo)
    adict.somekey = 'blah'
    self.assertEqual('blah', adict['somekey'])


class LazyPropertyTest(unittest.TestCase):

  class BaseClass(object):
    def __init__(self):
      self.prop_initialized = 0

    @type_utils.LazyProperty
    def myclass(self):
      self.prop_initialized += 1
      return LazyPropertyTest.BaseClass

  class DerivedClass(BaseClass):
    @type_utils.LazyProperty
    def myclass(self):
      self.prop_initialized += 1
      return LazyPropertyTest.DerivedClass

  def testGetterForBaseClass(self):
    obj = self.BaseClass()
    self.assertEqual(obj.myclass, self.BaseClass)
    self.assertEqual(obj.prop_initialized, 1)
    self.assertEqual(obj.myclass, self.BaseClass)
    self.assertEqual(obj.prop_initialized, 1)

  def testGetterForDerivedClass(self):
    obj = self.DerivedClass()
    self.assertEqual(obj.myclass, self.DerivedClass)
    self.assertEqual(obj.prop_initialized, 1)
    self.assertEqual(obj.myclass, self.DerivedClass)
    self.assertEqual(obj.prop_initialized, 1)

  def testSetByAssign(self):
    obj = self.BaseClass()
    with self.assertRaises(AttributeError):
      obj.myclass = 123

    obj = self.DerivedClass()
    with self.assertRaises(AttributeError):
      obj.myclass = 123

  def testSetByOverride(self):
    obj = self.BaseClass()
    type_utils.LazyProperty.Override(obj, 'myclass', 123)
    self.assertEqual(obj.prop_initialized, 0)
    self.assertEqual(obj.myclass, 123)


if __name__ == "__main__":
  unittest.main()
