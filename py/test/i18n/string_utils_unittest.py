#!/usr/bin/python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import re
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import string_utils
from cros.factory.test.i18n import translation
from cros.factory.test.i18n import unittest_test_case


class SafeFormatterTest(unittest.TestCase):

  def setUp(self):
    self.formatter = string_utils.SafeFormatter()
    self.formatter.Warn = lambda msg, *args: self.warnings.append(msg % args)
    self.warnings = []

  def AssertHasWarningRegexp(self, pattern):
    found = any(re.search(pattern, msg) for msg in self.warnings)
    self.assertTrue(found, '"%s" not found in warning messages.' % pattern)

  def testFormat(self):
    self.assertEqual("a 'b' 1",
                     self.formatter.format(
                         '{a} {b!r} {c:.0f}', a='a', b='b', c=1.234))

  def testVariableNotFound(self):
    self.assertEqual('[?]', self.formatter.format('{foo}'))
    self.AssertHasWarningRegexp('Key foo not found')

    self.assertEqual('[?] [?]',
                     self.formatter.format('{bar!s} {baz:3}',
                                           {'bar!s': 1, 'baz:3': 2}))
    self.AssertHasWarningRegexp('Key bar not found')
    self.AssertHasWarningRegexp('Key baz not found')

  def testPositionalArg(self):
    self.assertEqual('[?] 1 [?]', self.formatter.format('{-1} {0} {1}', 1))
    self.AssertHasWarningRegexp('Key -1 not found')
    self.AssertHasWarningRegexp(
        r'Using positional argument \{0\} is not recommended')
    self.AssertHasWarningRegexp(
        r'Using positional argument \{1\} is not recommended')

  def testEmptyPositionalArg(self):
    self.assertEqual('[?]', self.formatter.format('{}', 1))
    self.AssertHasWarningRegexp(
        r'Using positional argument \{\} is not supported')


class StringUtilsTest(unittest_test_case.I18nTestCase):

  def testStringJoin(self):
    self.assertEqual(
        {'en-US': '<div>English</div>', 'zh-CN': '<div>Chinese</div>'},
        string_utils.StringJoin(
            '<div>', {'en-US': 'English', 'zh-CN': 'Chinese'}, '</div>'))
    self.assertEqual(
        {'en-US': 'abcd', 'zh-CN': 'abCd'},
        string_utils.StringJoin(
            'a', {'en-US': 'b'}, {'en-US': 'c', 'zh-CN': 'C'}, 'd'))
    self.assertRaisesRegexp(ValueError, "doesn't contains default locale",
                            string_utils.StringJoin, 'a', {'zh-CN': 'b'})

  def testStringFormat(self):
    self.assertEqual(
        {'en-US': '{format string}', 'zh-CN': '{format string}'},
        string_utils.StringFormat('{{format string}}'))
    self.assertEqual(
        {'en-US': '[format string]', 'zh-CN': '[string format]'},
        string_utils.StringFormat(
            {'en-US': '[{str1} {str2}]', 'zh-CN': '[{str2} {str1}]'},
            str1='format', str2='string'))
    self.assertEqual(
        {'en-US': 'text 1', 'zh-CN': 'text 2'},
        string_utils.StringFormat(
            {'en-US': 'text {v}'}, v={'en-US': 1, 'zh-CN': 2}))
    self.assertEqual(
        {'en-US': 'format string text 1 text 2 [00042]',
         'zh-CN': '<00042>-text-2-text 1-format-string'},
        string_utils.StringFormat(
            'format string {str1} {str2} [{val1:05}]',
            str1='text 1', str2=translation._('text 2'), val1=42))

    self.assertRaisesRegexp(ValueError, "doesn't contains default locale",
                            string_utils.StringFormat, {'zh-CN': 'a'})
    self.assertRaisesRegexp(ValueError, "doesn't contains default locale",
                            string_utils.StringFormat, '{s}', s={'zh-CN': 'a'})
    self.assertEqual(
        {'en-US': '[?]', 'zh-CN': '[?]'},
        string_utils.StringFormat('{str}'))
    self.assertEqual(
        {'en-US': 'str', 'zh-CN': '[?]'},
        string_utils.StringFormat({'en-US': '{str}', 'zh-CN': '{str1}'},
                                  str='str'))


if __name__ == '__main__':
  unittest.main()
