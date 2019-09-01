#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for string_utils.py."""


import logging
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.utils.string_utils import DecodeUTF8
from cros.factory.utils.string_utils import ParseDict
from cros.factory.utils.string_utils import ParseString


_LINES = ['TPM Enabled: true',
          'TPM Owned: false',
          'TPM Being Owned: false',
          'TPM Ready: false',
          'TPM Password:',
          'Test: something1:something2']
_DICT_RESULT = {'TPM Being Owned': 'false',
                'TPM Ready': 'false',
                'TPM Password': '',
                'TPM Enabled': 'true',
                'TPM Owned': 'false',
                'Test': 'something1:something2'}


class DecodeUTF8Test(unittest.TestCase):
  """Unittest for DecodeUTF8."""

  def testDecodeUTF8(self):
    self.assertEquals(u'abc', DecodeUTF8('abc'))
    self.assertEquals(u'abc', DecodeUTF8(u'abc'))
    self.assertEquals(u'TEST 測試', DecodeUTF8(u'TEST 測試'))
    self.assertEquals(1, DecodeUTF8(1))


class ParseDictTest(unittest.TestCase):
  """Unittest for ParseDict."""

  def testParseDict(self):
    self.assertEquals(_DICT_RESULT, ParseDict(_LINES, ':'))


class ParseStringTest(unittest.TestCase):
  """Unittest for ParseString."""

  def testPaseString(self):
    self.assertEquals('abc', ParseString('abc'))
    self.assertEquals(True, ParseString('true'))
    self.assertEquals(True, ParseString('True'))
    self.assertEquals(False, ParseString('false'))
    self.assertEquals(False, ParseString('False'))
    self.assertEquals(None, ParseString('None'))
    self.assertEquals(123, ParseString('123'))

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
