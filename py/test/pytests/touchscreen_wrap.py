# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests touchscreen by drawing a warp-in pattern.

In this test, we split the screen in C x R blocks. We ask operators to
draw blocks in sequence. Right now the drawing pattern is:
  1. Starting from upper-left block, move to rightmost block.
  2. Then move down, left, up, to draw a outer retangular circle.
  3. Move to the inner upper-left block (1, 1), repeat 1-2.
  4. Until the center block is reached.

The index of block (x, y) is defined as:
  index =  x + y * xSegment (number of blocks in x-axis).
For, example, a 3x3 grid:
  0 1 2
  3 4 5
  6 7 8
The drawing sequence is: 0, 1, 2, 5, 8, 7, 6, 3, 4.

It uses Chrome event API to get touch events. Hence test logic is in
touchscreen.js.

dargs:
  x_segments: Number of segments in x-axis. (default: 5)
  y_segments: Number of segments in y-axis. (default: 5)
"""

import unittest

from cros.factory.test import test_ui
from cros.factory.test.args import Arg


_ID_CONTAINER = 'touchscreen-test-container'

# The style is in touchscreen_wrap.css
# The layout contains one div for touchscreen.
_HTML_TOUCHSCREEN = (
    '<link rel="stylesheet" type="text/css" href="touchscreen_wrap.css">'
    '<div id="%s"></div>\n' % _ID_CONTAINER)


class TouchscreenTest(unittest.TestCase):
  """Tests touchscreen by drawing blocks in sequence.

  Properties:
    self.ui: test ui.
  """
  ARGS = [
      Arg('x_segments', int, 'Number of segments in x-axis.',
          default=5),
      Arg('y_segments', int, 'Number of segments in y-axis.',
          default=5),
      Arg('retries', int, 'Number of retries.', default=5)]

  def setUp(self):
    # Initialize frontend presentation
    self.ui = test_ui.UI()
    self.ui.AppendHTML(_HTML_TOUCHSCREEN)
    self.ui.CallJSFunction('setupTouchscreenTest', _ID_CONTAINER,
                           self.args.x_segments, self.args.y_segments,
                           self.args.retries)

  def OnFailPressed(self):
    """Fails the test."""
    self.ui.CallJSFunction('failTest')

  def runTest(self):
    self.ui.BindKey(test_ui.ESCAPE_KEY, lambda _: self.OnFailPressed())
    self.ui.Run()
