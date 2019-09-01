#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import translation
from cros.factory.test.i18n import unittest_test_case


class TranslationTest(unittest_test_case.I18nTestCase):

  def testGetTranslation(self):
    self.assertEqual('text-1',
                     translation.GetTranslation('text 1', 'zh-CN'))
    self.assertEqual('text 1',
                     translation.GetTranslation('text 1', 'en-US'))
    self.assertEqual('untranslated',
                     translation.GetTranslation('untranslated', 'zh-CN'))
    self.assertEqual('', translation.GetTranslation('', 'zh-CN'))

  def testTranslation(self):
    self.assertEqual({'en-US': 'text 1', 'zh-CN': 'text-1'},
                     translation.Translation('text 1'))
    self.assertEqual({'en-US': 'untranslated', 'zh-CN': 'untranslated'},
                     translation.Translation('untranslated'))

  def testNoTranslation(self):
    self.assertEqual({'en-US': 'text 1', 'zh-CN': 'text 1'},
                     translation.NoTranslation('text 1'))
    self.assertEqual({'en-US': 'untranslated', 'zh-CN': 'untranslated'},
                     translation.NoTranslation('untranslated'))
    self.assertEqual({'en-US': 0xdeadbeef, 'zh-CN': 0xdeadbeef},
                     translation.NoTranslation(0xdeadbeef))

  def testTranslatedTranslate(self):
    self.assertEqual({'en-US': 'text 1', 'zh-CN': 'text-1'},
                     translation.Translated('text 1'))
    self.assertEqual({'en-US': 'text 1', 'zh-CN': 'text 2'},
                     translation.Translated(
                         {'en-US': 'text 1', 'zh-CN': 'text 2'}))
    self.assertEqual({'en-US': 'text 1', 'zh-CN': 'text 1'},
                     translation.Translated({'en-US': 'text 1'}))

  def testTranslatedNoTranslate(self):
    self.assertEqual({'en-US': 'text 1', 'zh-CN': 'text 1'},
                     translation.Translated('text 1', translate=False))
    self.assertEqual({'en-US': 'text 1', 'zh-CN': 'text 2'},
                     translation.Translated(
                         {'en-US': 'text 1', 'zh-CN': 'text 2'},
                         translate=False))
    self.assertEqual({'en-US': 'text 1', 'zh-CN': 'text 1'},
                     translation.Translated(
                         {'en-US': 'text 1'}, translate=False))

  def testTranslatedNoDefaultLocale(self):
    self.assertRaisesRegexp(
        ValueError, "doesn't contain the default locale",
        translation.Translated, {'zh-CN': 'zh'})
    self.assertRaisesRegexp(
        ValueError, "doesn't contain the default locale",
        translation.Translated, {'zh-CN': 'zh'}, translate=False)

  def testTranslatedUnicode(self):
    self.assertEqual({'en-US': 'en', 'zh-CN': u'\u4e2d\u6587'},
                     translation.Translated({
                         'en-US': 'en',
                         'zh-CN': '\xe4\xb8\xad\xe6\x96\x87'
                     }))

  def testGetAllTranslations(self):
    self.assertItemsEqual([
        {'en-US': 'text 1', 'zh-CN': 'text-1'},
        {'en-US': 'text 2', 'zh-CN': 'text-2'},
        {
            'en-US': 'format string {str1} {str2} [{val1:05}]',
            'zh-CN': '<{val1:05}>-{str2}-{str1}-format-string'
        }
    ], translation.GetAllTranslations())

if __name__ == '__main__':
  unittest.main()
