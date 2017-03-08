#!/usr/bin/python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import html_translator
from cros.factory.test.i18n import unittest_test_case
from cros.factory.utils import file_utils


class TranslateHTMLTest(unittest_test_case.I18nTestCase):

  def setUp(self):
    self.testdata_dir = os.path.join(unittest_test_case.TESTDATA_DIR,
                                     'html_translator')

  def GetTestData(self, filename):
    return file_utils.ReadFile(os.path.join(self.testdata_dir, filename))

  def testTranslateHTML(self):
    self.assertEqual(
        self.GetTestData('output.html'),
        html_translator.TranslateHTML(self.GetTestData('input.html')))

  def testTranslateHTMLError(self):
    self.assertRaisesRegexp(
        ValueError, 'Unexpected close tag',
        html_translator.TranslateHTML, self.GetTestData('unmatched_tag.html'))

    self.assertRaisesRegexp(
        ValueError, 'Found unclosed tag',
        html_translator.TranslateHTML, self.GetTestData('unclosed_tag.html'))


if __name__ == '__main__':
  unittest.main()
