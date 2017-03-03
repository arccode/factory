#!/usr/bin/python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import string_utils
from cros.factory.test.i18n import translation
from cros.factory.test.i18n import unittest_test_case


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
    self.assertRaisesRegexp(KeyError, 'str',
                            string_utils.StringFormat, '{str}')
    self.assertRaisesRegexp(KeyError, 'str1',
                            string_utils.StringFormat,
                            {'en-US': '{str}', 'zh-CN': '{str1}'}, str='str')

if __name__ == '__main__':
  unittest.main()
