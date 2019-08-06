#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Unittest for cros.factory.utils.type_utils."""

import unittest

import factory_common  # pylint: disable=unused-import
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


class FlattenTupleTest(unittest.TestCase):

  def runTest(self):
    self.assertEquals((), type_utils.FlattenTuple(()))
    self.assertEquals((), type_utils.FlattenTuple((())))
    self.assertEquals((1, ), type_utils.FlattenTuple((1, )))
    self.assertEquals((1, ), type_utils.FlattenTuple((1, ())))
    self.assertEquals((1, 2, 3, 4, 5, 6),
                      type_utils.FlattenTuple((1, 2, (3, 4, ()), 5, 6)))


class MakeListTest(unittest.TestCase):

  def runTest(self):
    self.assertEquals(['a'], type_utils.MakeList('a'))
    self.assertEquals(['abc'], type_utils.MakeList('abc'))
    self.assertEquals(['a', 'b'], type_utils.MakeList(['a', 'b']))
    self.assertEquals(['a', 'b'], type_utils.MakeList({'a': 'foo', 'b': 'bar'}))


class MakeTupleTest(unittest.TestCase):

  def runTest(self):
    self.assertEquals(('a',), type_utils.MakeTuple('a'))
    self.assertEquals(('abc',), type_utils.MakeTuple('abc'))
    self.assertEquals(('a', 'b'), type_utils.MakeTuple(['a', 'b']))
    self.assertEquals(
        ('a', 'b'), type_utils.MakeTuple({'a': 'foo', 'b': 'bar'}))
    self.assertEquals(
        (1, 2, (3, 4, ('str',))),
        type_utils.MakeTuple([1, 2, (3, 4, ['str'])]))


class MakeSetTest(unittest.TestCase):

  def runTest(self):
    self.assertEquals(set(['ab']), type_utils.MakeSet('ab'))
    self.assertEquals(set(['a', 'b']), type_utils.MakeSet(['a', 'b']))
    self.assertEquals(set(['a', 'b']), type_utils.MakeSet(('a', 'b')))
    self.assertEquals(set(['a', 'b']),
                      type_utils.MakeSet({'a': 'foo', 'b': 'bar'}))


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


class LazyObjectTest(unittest.TestCase):

  class BaseClass(object):

    def __init__(self, output):
      self.x = 0
      self.output = output
      self.output['init'] = True

    def inc(self):
      self.x += 1
      self.output['inc'] = True

  def testLazyCreation(self):
    o = {}
    a = type_utils.LazyObject(self.BaseClass, o)
    self.assertEqual(o.get('init'), None)
    self.assertEqual(a.x, 0)
    self.assertEqual(o.get('init'), True)

  def testVariableMember(self):
    o = {}
    a = type_utils.LazyObject(self.BaseClass, o)
    self.assertEqual(a.x, 0)
    a.inc()
    self.assertEqual(a.x, 1)


class CachedGetterTest(unittest.TestCase):

  def setUp(self):
    self.data = {'init': 0}

    @type_utils.CachedGetter
    def simple_getter():
      self.data['init'] += 1
      return self.data['init']

    @type_utils.CachedGetter
    def args_getter(v):
      return v + 1

    self.simple_getter = simple_getter
    self.args_getter = args_getter

  def testSimpleGetter(self):
    self.assertEquals(self.simple_getter(), 1)
    self.assertEquals(self.data['init'], 1)
    self.assertEquals(self.simple_getter(), 1)
    self.assertEquals(self.data['init'], 1)

    self.simple_getter.InvalidateCache()
    self.assertEquals(self.simple_getter(), 2)
    self.assertEquals(self.data['init'], 2)
    self.assertEquals(self.simple_getter(), 2)
    self.assertEquals(self.data['init'], 2)

    self.simple_getter.Override(3)
    self.assertEquals(self.simple_getter(), 3)
    self.assertEquals(self.data['init'], 2)
    self.assertEquals(self.simple_getter(), 3)
    self.assertEquals(self.data['init'], 2)

  def testArgsGetter(self):
    """Test getter with arguments.

    Currently we ignore different arguments and always return first cached
    value. The goal of this unit test function is to make sure this behavior
    won't change unexpectedly.

    If we decide to support multiple cached values, or invalidate whenever
    arguments are changed, please first make sure all users of CachedGetter
    won't have problem and then change this unit test.
    """
    self.assertEquals(self.args_getter(0), 1)
    self.assertEquals(self.args_getter(1), 1)
    self.assertEquals(self.args_getter(2), 1)

    self.args_getter.InvalidateCache()
    self.assertEquals(self.args_getter(2), 3)
    self.assertEquals(self.args_getter(1), 3)
    self.assertEquals(self.args_getter(0), 3)


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


class GetDictTest(unittest.TestCase):

  def testGet(self):
    GetDict = type_utils.GetDict
    data = {
        'blah': 1,
        'services': {
            'shop_floor': {
            }
        }
    }
    self.assertEquals(GetDict(data, 'blah'), 1)
    self.assertEquals(GetDict(data, 'non_exist'), None)
    self.assertEquals(GetDict(data, 'non_exist', True), True)
    self.assertEquals(GetDict(data, 'services.non_exist', 'N/A'), 'N/A')
    self.assertEquals(GetDict(data, 'services.shop_floor', 'FAIL'), {})
    self.assertEquals(GetDict(
        data, 'services.shop_floor.service_url', 'DEFAULT'), 'DEFAULT')


class UnicodeToStringTest(unittest.TestCase):

  def isSame(self, a, b):
    """Returns True if a and b are equal and the same type.

    This is necessary because 'abc' == u'abc' but we want to distinguish
    them.
    """
    # pylint: disable=unidiomatic-typecheck
    if a != b:
      return False
    elif type(a) != type(b):
      return False
    elif type(a) in [list, tuple]:
      for x, y in zip(a, b):
        if not self.isSame(x, y):
          return False
    elif isinstance(a, set):
      return self.isSame(sorted(list(a)), sorted(list(b)))
    elif isinstance(a, dict):
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


class BindFunctionTest(unittest.TestCase):

  def runTest(self):
    def func(a, b):
      """Adds two numbers."""
      return a + b

    bound_func = type_utils.BindFunction(func, 123, 151)
    self.assertEqual(274, bound_func())
    self.assertEqual(274, bound_func())
    self.assertEqual('func', bound_func.__name__)
    self.assertEqual('Adds two numbers.', bound_func.__doc__)


if __name__ == "__main__":
  unittest.main()
