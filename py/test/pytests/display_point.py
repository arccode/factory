# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""
A factory test to test the function of display panel using some points.
"""

import logging
import random
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection

_ID_CONTAINER = 'display-point-test-container'

# The style is in display_point.css
# The layout contains one div for display.
_HTML_DISPLAY = """
   <link rel="stylesheet" type="text/css" href="display_point.css">
   <div id="%s">
   </div>\n"""  % _ID_CONTAINER


class DisplayPointTest(unittest.TestCase):
  '''Tests the function of display panel using some points.

  There are two subtests in this test. The first one is black points on white
  background. The second one is white points on black background.
  There will be random number of points(1 to 3) in random places in
  each subtest.
  Attributes:
    self.ui: test ui.
    self.template: ui template handling html layout.
    self.list_number_point: a list of the number of points in each subtest.
  '''
  ARGS = [
    Arg('point_size', (float, int), 'width and height of testing point in px',
        optional=True, default=3.0),
    Arg('max_point_count', int, 'maximum number of points in each subtest',
        optional=True, default=3)
  ]

  def setUp(self):
    '''Initializes frontend presentation and properties.'''
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendHTML(_HTML_DISPLAY)
    self.list_number_point = [
        random.randint(1, self.args.max_point_count) for _ in xrange(2)]
    logging.info('testing point: %s',
                 ', '.join([str(x) for x in self.list_number_point]))
    self.ui.CallJSFunction('setupDisplayPointTest', _ID_CONTAINER,
                           self.list_number_point, float(self.args.point_size))

  def runTest(self):
    '''Sets the callback function of keys and run the test.'''
    self.ui.BindKey(' ', lambda _: self.OnSpacePressed())
    self.ui.BindKey(test_ui.ESCAPE_KEY, lambda _: self.OnFailPressed())
    self.ui.Run()

  def OnSpacePressed(self):
    '''Calls JS function to switch display on/off.'''
    self.ui.CallJSFunction('switchDisplayOnOff')

  def OnFailPressed(self):
    '''Fails the test.'''
    self.ui.CallJSFunction('failTest')
