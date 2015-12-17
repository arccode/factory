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


class UniqueSetTest(unittest.TestCase):
  def setUp(self):
    self.container = type_utils.UniqueStack()

  def testInsertThenGet(self):
    for x in [5, 1, 2, 4, 3]:
      self.container.Add(x)
      self.assertEqual(self.container.Get(), x)

  def testDeleteOlderObject(self):
    data = [5, 1, 2, 4, 3]
    for x in data:
      self.container.Add(x)

    last = data.pop()

    self.assertEqual(self.container.Get(), last)
    for x in data:
      self.container.Del(x)
      self.assertEqual(self.container.Get(), last)

  def testInsertExistingObject(self):
    data = [5, 4, 3, 2, 1, 0]
    for x in data:
      self.container.Add(x)

    for x in data:
      self.container.Add(x)
      self.assertEqual(self.container.Get(), 0)

  def testGetAfterDelete(self):
    for x in xrange(5):
      self.container.Add(x)

    for x in xrange(4, 0, -1):
      self.container.Del(x)
      self.assertEqual(self.container.Get(), x - 1)

  def testInsertAfterDelete(self):
    self.container.Add(1)
    self.container.Add(2)
    self.container.Del(1)
    self.assertEqual(self.container.Get(), 2)
    self.container.Add(1)
    self.assertEqual(self.container.Get(), 1)


if __name__ == "__main__":
  unittest.main()
