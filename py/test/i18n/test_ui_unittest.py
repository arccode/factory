#!/usr/bin/python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import re
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import test_ui
from cros.factory.test.i18n import translation
from cros.factory.test.i18n import unittest_test_case


class TestUITest(unittest_test_case.I18nTestCase):

  def AssertSpansEqual(self, spans, html):
    self.assertItemsEqual(re.findall('<span.*?</span>', html), spans)

  def testMakeI18nLabel(self):
    self.AssertSpansEqual(
        ['<span class="goofy-label-en-US">text 1</span>',
         '<span class="goofy-label-zh-CN">text-1</span>'],
        test_ui.MakeI18nLabel('text 1'))
    self.AssertSpansEqual(
        ['<span class="goofy-label-en-US">text 1</span>',
         '<span class="goofy-label-zh-CN">text-1</span>'],
        test_ui.MakeI18nLabel(translation._('text 1')))
    self.AssertSpansEqual(
        ['<span class="goofy-label-en-US"><b>text 1 text 2</b></span>',
         '<span class="goofy-label-zh-CN"><b>text-1 text 2</b></span>'],
        test_ui.MakeI18nLabel('<b>{str1} {str2}</b>',
                              str1=translation._('text 1'), str2='text 2'))
    self.AssertSpansEqual(
        ['<span class="goofy-label-en-US">format string 1 2 [34567]</span>',
         '<span class="goofy-label-zh-CN"><76543>-2-1-format-string</span>'],
        test_ui.MakeI18nLabel(
            'format string {str1} {str2} [{val1:05}]',
            str1='1', str2=translation._('2'),
            val1={'en-US': 34567, 'zh-CN': 76543}))

  def testMakeI18nLabelWithClass(self):
    self.AssertSpansEqual(
        ['<span class="goofy-label-en-US">text 1</span>',
         '<span class="goofy-label-zh-CN">text-1</span>'],
        test_ui.MakeI18nLabelWithClass('text 1', ''))
    self.AssertSpansEqual(
        ['<span class="goofy-label-en-US large"><b>text 1 text 2</b></span>',
         '<span class="goofy-label-zh-CN large"><b>text-1 text 2</b></span>'],
        test_ui.MakeI18nLabelWithClass(
            '<b>{str1} {str2}</b>', 'large',
            str1=translation._('text 1'), str2='text 2'))

if __name__ == '__main__':
  unittest.main()
