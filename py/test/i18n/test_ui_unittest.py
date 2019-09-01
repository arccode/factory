#!/usr/bin/env python2
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
        test_ui.MakeI18nLabel(translation.Translation('text 1')))


if __name__ == '__main__':
  unittest.main()
