#!/usr/bin/env python3
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import unittest

from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test.i18n import translation
from cros.factory.test.i18n import unittest_test_case
from cros.factory.utils import arg_utils


class MockPyTest:
  """A mocked pytest with given ARGS."""
  def __init__(self, args):
    self.ARGS = args
    self.parser = arg_utils.Args(*self.ARGS)
    self.args = None

  def Parse(self, dargs):
    self.args = self.parser.Parse(dargs)


class ArgUtilsTest(unittest_test_case.I18nTestCase):

  def testI18nArg(self):
    test = MockPyTest([i18n_arg_utils.I18nArg('text', 'text.')])
    test.Parse({'text': translation.Translation('text 1')})
    self.assertEqual({'en-US': 'text 1', 'zh-CN': 'text-1'}, test.args.text)

    test.Parse({'text': 'text 1'})
    self.assertEqual({'en-US': 'text 1', 'zh-CN': 'text-1'}, test.args.text)

    self.assertRaisesRegex(ValueError, 'Required argument text not specified',
                           test.Parse, {})

  def testI18nArgWithDefault(self):
    test = MockPyTest([
        i18n_arg_utils.I18nArg('text', 'text.',
                               default={'en-US': 'en', 'zh-CN': 'zh'})])

    test.Parse({'text': translation.Translation('text 1')})
    self.assertEqual({'en-US': 'text 1', 'zh-CN': 'text-1'}, test.args.text)

    test.Parse({'text': 'text 1'})
    self.assertEqual({'en-US': 'text 1', 'zh-CN': 'text-1'}, test.args.text)

    test.Parse({})
    self.assertEqual({'en-US': 'en', 'zh-CN': 'zh'}, test.args.text)


if __name__ == '__main__':
  unittest.main()
