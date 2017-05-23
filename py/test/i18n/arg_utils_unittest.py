#!/usr/bin/python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test.i18n import translation
from cros.factory.test.i18n import unittest_test_case
from cros.factory.utils import arg_utils


class MockPyTest(object):
  """A mocked pytest with given ARGS."""
  def __init__(self, args):
    self.ARGS = args
    self.parser = arg_utils.Args(*self.ARGS)
    self.args = None

  def Parse(self, dargs):
    self.args = self.parser.Parse(dargs)


class ArgUtilsTest(unittest_test_case.I18nTestCase):

  def _ParsePyTest(self, test, i18n_arg_name, dargs):
    test.Parse(dargs)
    i18n_arg_utils.ParseArg(test, i18n_arg_name)

  def testI18nArg(self):
    test = MockPyTest([i18n_arg_utils.I18nArg('text', 'text.')])
    self._ParsePyTest(test, 'text', {'text': translation._('text 1')})
    self.assertEqual({'en-US': 'text 1', 'zh-CN': 'text-1'}, test.args.text)

    self._ParsePyTest(test, 'text', {'text': 'text 1'})
    self.assertEqual({'en-US': 'text 1', 'zh-CN': 'text-1'}, test.args.text)

    self.assertRaisesRegexp(ValueError, 'text is mandatory',
                            self._ParsePyTest, test, 'text', {})

  def testI18nArgWithDefault(self):
    test = MockPyTest([
        i18n_arg_utils.I18nArg('text', 'text.',
                               default={'en-US': 'en', 'zh-CN': 'zh'})])

    self._ParsePyTest(test, 'text', {'text': translation._('text 1')})
    self.assertEqual({'en-US': 'text 1', 'zh-CN': 'text-1'}, test.args.text)

    self._ParsePyTest(test, 'text', {'text': 'text 1'})
    self.assertEqual({'en-US': 'text 1', 'zh-CN': 'text-1'}, test.args.text)

    self._ParsePyTest(test, 'text', {})
    self.assertEqual({'en-US': 'en', 'zh-CN': 'zh'}, test.args.text)

  # ParseArg is already tested in previous two tests.

if __name__ == '__main__':
  unittest.main()
