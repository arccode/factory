# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""
A factory test to test the function of display.
"""

import unittest

from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection

_ID_CONTAINER = 'display-test-container'

# The style is in display.css
# The layout contains one div for display.
_HTML_DISPLAY = (
    '<link rel="stylesheet" type="text/css" href="display.css">'
    '<div id="%s"></div>\n' % _ID_CONTAINER)


class DisplayTest(unittest.TestCase):
  '''
  Tests the function of display.
  Properties:
    self.ui: test ui.
    self.template: ui template handling html layout.
    self.checked: user has check the display of current subtest.
    self.fullscreen: the test ui is in fullscreen or not.
  '''
  ARGS = [
    Arg('colors', list,
        """Set colors. Available colors are
        "solid-gray-170",
        "solid-gray-127",
        "solid-gray-63",
        "solid-red",
        "solid-green",
        "solid-blue",
        "solid-white",
        "solid-gray",
        "solid-black",
        "grid",
        "rectangle",
        "gradient-red",
        "gradient-green",
        "gradient-blue",
        "gradient-white"
        """,
        default= ["solid-gray-170", "solid-gray-127", "solid-gray-63",
                  "solid-red", "solid-green", "solid-blue"],
        optional=True),
  ]

  def setUp(self):
    '''Initializes frontend presentation and properties.'''
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendHTML(_HTML_DISPLAY)
    self.ui.CallJSFunction('setupDisplayTest', _ID_CONTAINER, self.args.colors)
    self.checked = False
    self.fullscreen = False

  def tearDown(self):
    return

  def runTest(self):
    '''Sets the callback function of keys and run the test.'''
    self.ui.BindKey(' ', lambda _: self.OnSpacePressed())
    self.ui.BindKey(test_ui.ENTER_KEY, lambda _: self.OnEnterPressed())
    self.ui.BindKey(test_ui.ESCAPE_KEY, lambda _: self.OnFailPressed())
    self.ui.Run()

  def OnSpacePressed(self):
    '''Sets self.checked to True.Calls JS function to switch display on/off.'''
    self.checked = True
    self.ui.CallJSFunction('switchDisplayOnOff')
    self.fullscreen = not self.fullscreen

  def OnEnterPressed(self):
    '''Passes the subtest only if self.checked is True.'''
    if self.checked:
      self.ui.CallJSFunction('passSubTest')
      # If the next subtest will be in fullscreen mode, checked should be True
      self.checked = self.fullscreen

  def OnFailPressed(self):
    '''Fails the subtest only if self.checked is True.'''
    if self.checked:
      self.ui.CallJSFunction('failSubTest')
      # If the next subtest will be in fullscreen mode, checked should be True
      self.checked = self.fullscreen
