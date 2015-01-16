#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611

import unittest
from cros.factory.test.unicode_to_string \
  import UnicodeToString, UnicodeToStringArgs, UnicodeToStringClass

# My favorite character: 囧
JIONG_UTF8 = '\xe5\x9b\xa7'


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
    self.assertSame(1, UnicodeToString(1))
    self.assertSame('abc', UnicodeToString(u'abc'))
    self.assertSame(JIONG_UTF8, UnicodeToString(u'囧'))

  def testUnicodeToStringArgs(self):
    @UnicodeToStringArgs
    def func(*args, **kwargs):
      return ('func', args, kwargs)

    self.assertSame(('func', ('a',), {'b': 'c'}),
                    func(u'a', b=u'c'))

  def testUnicodeToStringClass(self):
    @UnicodeToStringClass
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


if __name__ == '__main__':
  unittest.main()
