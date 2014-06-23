# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory test for lightbar on A case."""


import logging
import unittest

import factory_common   # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.utils import process_utils


_TEST_TITLE = test_ui.MakeLabel('Lightbar Test', u'光棒测试')
_TEST_PROMPT = lambda color_en, color_zh: test_ui.MakeLabel(
    'Is the lightbar %s?<br>Press SPACE if yes, "f" if no.' % color_en,
    u'光棒是否为%s？<br>是请按空白键，不是请按 f 。' % color_zh)
_CSS = 'body { font-size: 2em; }'


class LightbarTest(unittest.TestCase):
  """Factory test for lightbar on A case."""

  ARGS = [
      Arg('colors_to_test', type=(tuple, list),
          help=('a list of colors to test; each element of the list is a tuple '
                'of ((label_en, label_zh), [LED, RED, GREEN, BLUE])'),
          default=[
              (('red', u'红色'), [4, 255, 0, 0]),
              (('green', u'绿色'), [4, 0, 255, 0]),
              (('blue', u'蓝色'), [4, 0, 0, 255]),
              (('dark', u'全暗'), [4, 0, 0, 0]),
              (('white', u'白色'), [4, 255, 255, 255]),
          ]),
  ]

  def setUp(self):
    self._ui = test_ui.UI(css=_CSS)
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._test_color_index = 0
    self._ui.BindKey(' ', self.TestNextColorOrPass)
    self._ui.BindKey('F', self.FailTest)
    self.ECToolLightbar(['on'])
    self.ECToolLightbar(['init'])
    self.ECToolLightbar(['seq', 'stop'])

  def tearDown(self):
    self.ECToolLightbar(['seq', 'run'])

  def ECToolLightbar(self, args):
    """Calls 'ectool lightbar' with the given args.

    Args:
      args: The args to pass along with 'ectool lightbar'.

    Returns:
      The output of 'ectool lightbar'.

    Raises:
      FactoryTestFailure if the ectool command fails.
    """
    try:
      # Convert each arg to str to make subprocess module happy.
      args = [str(x) for x in args]
      return process_utils.CheckOutput(['ectool', 'lightbar'] + args, log=True)
    except Exception as e:  # pylint: disable=W0703
      raise factory.FactoryTestFailure('Unable to set lightbar: %s' % e)

  def TestColor(self, color_index):
    """Tests the color specified by the given index.

    Args:
      color_index: The index of self.args.colors_to_test to test.
    """
    labels, lrgb = self.args.colors_to_test[color_index]
    logging.info('Testing %s (%s)...', labels[0], lrgb)
    self._template.SetState(_TEST_PROMPT(*labels))
    self.ECToolLightbar(lrgb)

  def TestNextColorOrPass(self, _):
    """Callback function for keypress event of space key."""
    self._test_color_index += 1
    if self._test_color_index >= len(self.args.colors_to_test):
      self._ui.Pass()
    else:
      self.TestColor(self._test_color_index)

  def FailTest(self, _):
    """Callback function for keypress event of f key."""
    labels, _ = self.args.colors_to_test[self._test_color_index]
    self._ui.Fail('Lightbar failed to light up in %s' % labels[0])

  def runTest(self):
    self.TestColor(self._test_color_index)
    self._ui.Run()
