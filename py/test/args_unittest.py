#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.args import Arg, Args
from cros.factory.test.utils import Enum


class ArgsTest(unittest.TestCase):
  def setUp(self):
    self.parser = Args(
        Arg('required', str, 'X'),
        Arg('has_default', str, 'X', default='DEFAULT_VALUE'),
        Arg('optional', str, 'X', optional=True),
        Arg('int_typed', int, 'X', optional=True),
        Arg('int_or_string_typed', (int, str), 'X', optional=True),
        Arg('enum_typed', Enum(['a','b']), 'X', optional=True))

  def Parse(self, dargs):
    '''Parses dargs.

    Returns:
      A dictionary of attributes from the resultant object.
    '''
    values = self.parser.Parse(dargs)
    return dict((k, v) for k, v in values.__dict__.iteritems()
                if not k.startswith('_'))

  def testIntOrNone(self):
    self.parser = Args(
        Arg('int_or_none', (int, type(None)), 'X', default=5))
    self.assertEquals(dict(int_or_none=5),
                      self.Parse(dict()))
    self.assertEquals(dict(int_or_none=10),
                      self.Parse(dict(int_or_none=10)))
    self.assertEquals(dict(int_or_none=None),
                      self.Parse(dict(int_or_none=None)))

  def testRequired(self):
    self.assertEquals({'has_default': 'DEFAULT_VALUE',
                       'required': 'x',
                       'optional': None,
                       'int_or_string_typed': None,
                       'int_typed': None,
                       'enum_typed': None},
                      self.Parse(dict(required='x')))
    self.assertRaises(ValueError, lambda: self.Parse(dict()))
    self.assertRaises(ValueError, lambda: self.Parse(dict(required=None)))
    self.assertRaises(ValueError, lambda: self.Parse(dict(required=3)))

  def testOptional(self):
    self.assertEquals({'has_default': 'DEFAULT_VALUE',
                       'required': 'x',
                       'optional': 'y',
                       'int_or_string_typed': None,
                       'int_typed': None,
                       'enum_typed': None},
                      self.Parse(dict(required='x', optional='y')))
    self.assertEquals({'has_default': 'DEFAULT_VALUE',
                       'required': 'x',
                       'optional': None,
                       'int_or_string_typed': None,
                       'int_typed': None,
                       'enum_typed': None},
                      self.Parse(dict(required='x', optional=None)))

  def testInt(self):
    self.assertEquals({'has_default': 'DEFAULT_VALUE',
                       'required': 'x',
                       'optional': None,
                       'int_or_string_typed': None,
                       'int_typed': 3,
                       'enum_typed': None},
                      self.Parse(dict(required='x', int_typed=3)))
    self.assertRaises(ValueError, self.Parse, dict(required='x', int_typed='3'))

  def testEnum(self):
    self.assertEquals(
        {'has_default': 'DEFAULT_VALUE',
         'required': 'x',
         'optional': None,
         'int_or_string_typed': None,
         'int_typed': 3,
         'enum_typed': 'a'},
        self.Parse(dict(required='x', int_typed=3, enum_typed='a')))
    self.assertRaisesRegexp(ValueError,
                            'Argument enum_typed should have type \(Enum',
                            self.Parse, dict(required='x', enum_typed='c'))

  def testIntOrString(self):
    for value in (3, 'x'):
      self.assertEquals({'has_default': 'DEFAULT_VALUE',
                         'required': 'x',
                         'optional': None,
                         'int_or_string_typed': value,
                         'int_typed': None,
                         'enum_typed': None},
                        self.Parse(dict(required='x',
                                        int_or_string_typed=value)))
    # Wrong type
    self.assertRaises(
        ValueError,
        self.Parse, dict(required='x', int_or_string_typed=1.0))


if __name__ == '__main__':
  unittest.main()
