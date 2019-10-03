# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory test for lightbar on A case."""


import logging

from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils


class LightbarTest(test_case.TestCase):
  """Factory test for lightbar on A case."""

  ARGS = [
      Arg('colors_to_test', type=list,
          help=('a list of colors to test; each element of the list is '
                '[label, [LED, RED, GREEN, BLUE]]'),
          default=[
              [_('red'), [4, 255, 0, 0]],
              [_('green'), [4, 0, 255, 0]],
              [_('blue'), [4, 0, 0, 255]],
              [_('dark'), [4, 0, 0, 0]],
              [_('white'), [4, 255, 255, 255]],
          ]),
  ]

  def setUp(self):
    self.ECToolLightbar('on')
    self.ECToolLightbar('init')
    self.ECToolLightbar('seq', 'stop')
    self.colors_to_test = [
        (i18n.Translated(label), color)
        for label, color in self.args.colors_to_test
    ]
    self.ui.ToggleTemplateClass('font-large', True)

  def tearDown(self):
    self.ECToolLightbar('seq', 'run')

  def ECToolLightbar(self, *args):
    """Calls 'ectool lightbar' with the given args.

    Args:
      args: The args to pass along with 'ectool lightbar'.

    Raises:
      TestFailure if the ectool command fails.
    """
    try:
      # Convert each arg to str to make subprocess module happy.
      args = [str(x) for x in args]
      process_utils.CheckOutput(['ectool', 'lightbar'] + args, log=True)
    except Exception as e:
      raise type_utils.TestFailure('Unable to set lightbar: %s' % e)

  def runTest(self):
    for color_label, lrgb in self.colors_to_test:
      color_name = color_label['en-US']
      logging.info('Testing %s (%s)...', color_name, lrgb)
      self.ECToolLightbar(*lrgb)
      self.ui.SetState(
          _('Is the lightbar {color}?<br>Press SPACE if yes, "F" if no.',
            color=color_label))
      key = self.ui.WaitKeysOnce([test_ui.SPACE_KEY, 'F'])
      if key == 'F':
        self.FailTask('Lightbar failed to light up in %s' % color_name)
