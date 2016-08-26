#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Unittest for cros.factory.utils.type_utils."""

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils import type_utils


# Jon's favorite character for Unicode testing: 囧
JIONG_UTF8 = '\xe5\x9b\xa7'


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

    @type_utils.LazyProperty
    def base_prop(self):
      return 'base_prop'

  class DerivedClass(BaseClass):
    @type_utils.LazyProperty
    def myclass(self):
      self.prop_initialized += 1
      return LazyPropertyTest.DerivedClass

    @type_utils.LazyProperty
    def derived_prop(self):
      return 'derived_prop'

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

  def testSetByOverrideOnBaseClass(self):
    obj = self.BaseClass()
    type_utils.LazyProperty.Override(obj, 'myclass', 123)
    self.assertEqual(obj.prop_initialized, 0)
    self.assertEqual(obj.myclass, 123)

    type_utils.LazyProperty.Override(obj, 'base_prop', 456)
    self.assertEqual(obj.base_prop, 456)

  def testSetByOverrideOnDerivedClass(self):
    obj = self.DerivedClass()
    type_utils.LazyProperty.Override(obj, 'myclass', 123)
    self.assertEqual(obj.prop_initialized, 0)
    self.assertEqual(obj.myclass, 123)

    type_utils.LazyProperty.Override(obj, 'base_prop', 456)
    self.assertEqual(obj.base_prop, 456)

    type_utils.LazyProperty.Override(obj, 'derived_prop', 789)
    self.assertEqual(obj.derived_prop, 789)


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


class UnicodeToStringTest(unittest.TestCase):

  def isSame(self, a, b):
    '''Returns True if a and b are equal and the same type.

    This is necessary because 'abc' == u'abc' but we want to distinguish
    them.
    '''
    if a != b:
      return False
    elif type(a) != type(b):
      return False
    elif type(a) in [list, tuple]:
      for x, y in zip(a, b):
        if not self.isSame(x, y):
          return False
    elif type(a) == set:
      return self.isSame(sorted(list(a)), sorted(list(b)))
    elif type(a) == dict:
      for k in a:
        if not self.isSame(a[k], b[k]):
          return False
    return True

  def assertSame(self, a, b):
    self.assertTrue(self.isSame(a, b), 'isSame(%r,%r)' % (a, b))

  def testAssertSame(self):
    """Makes sense that assertSame works properly."""
    self.assertSame('abc', 'abc')
    self.assertRaises(AssertionError,
                      lambda: self.assertSame('abc', u'abc'))
    self.assertSame(['a'], ['a'])
    self.assertRaises(AssertionError,
                      lambda: self.assertSame(['a'], [u'a']))
    self.assertSame(('a'), ('a'))
    self.assertRaises(AssertionError,
                      lambda: self.assertSame(('a'), (u'a')))
    self.assertSame(set(['a']), set(['a']))
    self.assertRaises(
        AssertionError,
        lambda: self.assertSame(set(['a']),
                                set([u'a'])))
    self.assertSame({1: 'a'}, {1: 'a'})
    self.assertRaises(AssertionError,
                      lambda: self.assertSame({1: 'a'}, {1: u'a'}))

  def testUnicodeToString(self):
    self.assertSame(1, type_utils.UnicodeToString(1))
    self.assertSame('abc', type_utils.UnicodeToString(u'abc'))
    self.assertSame(JIONG_UTF8, type_utils.UnicodeToString(u'囧'))

  def testUnicodeToStringArgs(self):
    @type_utils.UnicodeToStringArgs
    def func(*args, **kwargs):
      return ('func', args, kwargs)

    self.assertSame(('func', ('a',), {'b': 'c'}),
                    func(u'a', b=u'c'))

  def testUnicodeToStringClass(self):
    @type_utils.UnicodeToStringClass
    class MyClass(object):

      def f1(self, *args, **kwargs):
        return ('f1', args, kwargs)

      def f2(self, *args, **kwargs):
        return ('f2', args, kwargs)

    obj = MyClass()
    self.assertSame(('f1', ('a',), {'b': 'c', 'd': set(['e'])}),
                    obj.f1(u'a', b=u'c', d=set([u'e'])))
    self.assertSame(('f2', ('a',), {'b': 'c', 'd': set(['e'])}),
                    obj.f2(u'a', b=u'c', d=set([u'e'])))


if __name__ == "__main__":
  unittest.main()
