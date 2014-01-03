#!/usr/bin/env python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.simple_shopfloor import LoadAuxCsvData


class LoadAuxCsvDataTest(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.NamedTemporaryFile()

  def tearDown(self):
    self.tmp.close()

  def _WriteValidRows(self):
    print >> self.tmp, "id,a_bool[bool],a_str[str],a_int[int],a_float[float]"
    print >> self.tmp, "1,True,foo,111,.5"
    print >> self.tmp, "2,1,foo,111,.5"
    print >> self.tmp, "3,true,foo,111,.5"
    print >> self.tmp, "4,False,bar,222,1.5"
    print >> self.tmp, "6,false,bar,222,1.5"
    print >> self.tmp, "5,0,bar,222,1.5"

  def _ReadData(self):
    self.tmp.flush()
    return LoadAuxCsvData(self.tmp.name)

  def testValid(self):
    self._WriteValidRows()
    self.assertEqual(
        {'1': {'id': '1',
               'a_bool': True, 'a_str': 'foo', 'a_int': 111, 'a_float': 0.5},
         '2': {'id': '2',
               'a_bool': True, 'a_str': 'foo', 'a_int': 111, 'a_float': 0.5},
         '3': {'id': '3',
               'a_bool': True, 'a_str': 'foo', 'a_int': 111, 'a_float': 0.5},
         '4': {'id': '4',
               'a_bool': False, 'a_str': 'bar', 'a_int': 222, 'a_float': 1.5},
         '5': {'id': '5',
               'a_bool': False, 'a_str': 'bar', 'a_int': 222, 'a_float': 1.5},
         '6': {'id': '6',
               'a_bool': False, 'a_str': 'bar', 'a_int': 222, 'a_float': 1.5}},
        self._ReadData())

  def testDuplicateID(self):
    self._WriteValidRows()
    print >> self.tmp, "1,False,foo,222,.5"
    self.assertRaisesRegexp(ValueError,
                            r"^In \S+:8, duplicate ID '1'$",
                            self._ReadData)

  def testInvalidBoolean(self):
    self._WriteValidRows()
    print >> self.tmp, "1,x,foo,222,.5"
    self.assertRaisesRegexp(ValueError,
                            r"^In \S+:8\.a_bool, 'x' is not a Boolean value$",
                            self._ReadData)

  def testInvalidInt(self):
    self._WriteValidRows()
    print >> self.tmp, "1,True,foo,x,.5"
    self.assertRaisesRegexp(ValueError,
                            r"^In \S+:8\.a_int, invalid literal",
                            self._ReadData)

  def testDuplicateHeader(self):
    print >> self.tmp, "id,a,a"
    self.assertRaisesRegexp(ValueError,
                            r"^In \S+, more than one column named 'a'",
                            self._ReadData)

  def testBadHeader(self):
    print >> self.tmp, "id,a["
    self.assertRaisesRegexp(ValueError,
                            r"^In \S+, header 'a\[' does not match regexp",
                            self._ReadData)

  def testUnknownType(self):
    print >> self.tmp, "id,a[foo]"
    self.assertRaisesRegexp(ValueError,
                            (r"^In \S+, header 'a' has unknown type 'foo' "
                             r"\(should be one of "
                             r"\['bool', 'float', 'int', 'str'\]\)"),
                            self._ReadData)

if __name__ == '__main__':
  unittest.main()
