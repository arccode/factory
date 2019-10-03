# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""A factory test to test the function of display panel using some points.
"""

import collections
import logging
import random

from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg


_TestItem = collections.namedtuple('TestItem', 'num_point bg_color point_color')


class DisplayPointTest(test_case.TestCase):
  """Tests the function of display panel using some points.

  There are two subtests in this test. The first one is black points on white
  background. The second one is white points on black background.
  There will be random number of points(1 to 3) in random places in
  each subtest.

  Attributes:
    list_number_point: a list of the number of points in each subtest.
  """
  ARGS = [
      Arg('point_size', (float, int), 'width and height of testing point in px',
          default=3.0),
      Arg('max_point_count', int, 'maximum number of points in each subtest',
          default=3)
  ]

  def setUp(self):
    """Initializes frontend presentation and properties."""
    if self.args.max_point_count >= 10:
      raise ValueError('>= 10 points is not supported')

    self.items = [
        _TestItem(
            random.randint(1, self.args.max_point_count), 'white', 'black'),
        _TestItem(
            random.randint(1, self.args.max_point_count), 'black', 'white')
    ]
    logging.info('testing point: %s',
                 ', '.join(str(item.num_point) for item in self.items))
    self._frontend_proxy = self.ui.InitJSTestObject(
        'DisplayPointTest', self.args.point_size)
    self.event_loop.AddEventHandler(
        'toggle-display', lambda unused_event: self.ToggleDisplay())
    self.display = False
    self.checked = False

  def runTest(self):
    """Sets the callback function of keys and run the test."""
    all_keys = [test_ui.SPACE_KEY, test_ui.ESCAPE_KEY]
    all_keys.extend(str(k) for k in range(1, self.args.max_point_count + 1))
    for idx, item in enumerate(self.items):
      self._frontend_proxy.SetupPoints(item.num_point, item.bg_color,
                                       item.point_color)
      if idx > 0 and not self.display:
        self.ToggleDisplay()

      while True:
        key = self.ui.WaitKeysOnce(all_keys)
        if key == test_ui.SPACE_KEY:
          self.ToggleDisplay()
        elif key == test_ui.ESCAPE_KEY:
          self.FailTask(
              'DisplayPoint test failed at item %d: Mark failed by operator.' %
              idx)
        else:
          if not self.checked:
            continue
          input_num = int(key)
          if input_num == item.num_point:
            break
          self.FailTask('DisplayPoint test failed at item %d:'
                        ' Correct number: %d, Input number: %d' %
                        (idx, item.num_point, input_num))

  def ToggleDisplay(self):
    if self.display:
      self._frontend_proxy.SwitchDisplayOff()
    else:
      self._frontend_proxy.SwitchDisplayOn()
      self.checked = True
    self.display = not self.display
