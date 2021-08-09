#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for string_utils.py."""


import logging
import unittest

from cros.factory.utils.string_utils import DecodeUTF8
from cros.factory.utils.string_utils import ParseDict
from cros.factory.utils.string_utils import ParseString
from cros.factory.utils.string_utils import ParseUrl


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

_LINES_RECUSIVE = """\
TPM:
  Enabled: true
  Owned: false
  Being Owned: false
  Ready: false
  Password:
Test: something1:something2
"""

_LINES_RECUSIVE_MISALIGNED = """\
 TPM:
   Enabled: true
   Owned: false
   Being Owned: false
   Ready: false
######
   Password:
Test: something1:something2
""".replace('#', ' ')  # to pass style check

_LINES_RECUSIVE_INVALID = """\
TPM:
  Enabled true
Test: something1:something2
"""

_DICT_RESULT_RECURSIVE = {
    'TPM': {
        'Being Owned': 'false',
        'Ready': 'false',
        'Password': '',
        'Enabled': 'true',
        'Owned': 'false',
    },
    'Test': 'something1:something2'
}


class DecodeUTF8Test(unittest.TestCase):
  """Unittest for DecodeUTF8."""

  def testDecodeUTF8(self):
    self.assertEqual(u'abc', DecodeUTF8('abc'))
    self.assertEqual(u'abc', DecodeUTF8(u'abc'))
    self.assertEqual(u'TEST 測試', DecodeUTF8(u'TEST 測試'))
    self.assertEqual(1, DecodeUTF8(1))


class ParseDictTest(unittest.TestCase):
  """Unittest for ParseDict."""

  def testParseDict(self):
    self.assertEqual(_DICT_RESULT, ParseDict(_LINES, ':'))

  def testParseDictRecursive(self):
    self.assertEqual(
        _DICT_RESULT_RECURSIVE,
        ParseDict(_LINES_RECUSIVE.splitlines(), ':', recursive=True))
    self.assertEqual(
        _DICT_RESULT_RECURSIVE,
        ParseDict(_LINES_RECUSIVE_MISALIGNED.splitlines(), ':', recursive=True))

    self.assertRaises(ValueError, ParseDict,
                      _LINES_RECUSIVE_INVALID.splitlines(), ':', recursive=True)
    self.assertRaises(ValueError, ParseDict, _LINES_RECUSIVE.splitlines(), '-',
                      recursive=True)


class ParseStringTest(unittest.TestCase):
  """Unittest for ParseString."""

  def testPaseString(self):
    self.assertEqual('abc', ParseString('abc'))
    self.assertEqual(True, ParseString('true'))
    self.assertEqual(True, ParseString('True'))
    self.assertEqual(False, ParseString('false'))
    self.assertEqual(False, ParseString('False'))
    self.assertEqual(None, ParseString('None'))
    self.assertEqual(123, ParseString('123'))


class ParseUrlTest(unittest.TestCase):
  """Unittest for ParseUrl."""

  def testParseUrl(self):
    self.assertEqual(dict(scheme='https', host='example.com', port='8080'),
                     ParseUrl('https://example.com:8080'))
    self.assertEqual(dict(scheme='ftp', user='user', password='pass',
                          host='192.168.1.1', path='/foo/bar.zip'),
                     ParseUrl('ftp://user:pass@192.168.1.1/foo/bar.zip'))
    self.assertEqual(dict(scheme='ssh', user='user', password='pass',
                          host='192.168.1.1', port='2222'),
                     ParseUrl('ssh://user:pass@192.168.1.1:2222'))
    self.assertEqual(dict(scheme='smb', user='192.168.1.2/user',
                          password='pass', host='host', port='2222',
                          path='/public'),
                     ParseUrl('smb://192.168.1.2/user:pass@host:2222/public'))
    self.assertEqual(dict(), ParseUrl('invalid.com'))

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
