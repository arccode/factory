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
    self.checked: user has already pressed spacebar for each subtest.
  '''

  def setUp(self):
    '''Initializes frontend presentation and properties.'''
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendHTML(_HTML_DISPLAY)
    self.ui.CallJSFunction('setupDisplayTest', _ID_CONTAINER)
    self.checked = False

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

  def OnEnterPressed(self):
    '''Passes the subtest only if self.checked is True.'''
    if self.checked:
      self.ui.CallJSFunction('passSubTest')
      self.checked = False

  def OnFailPressed(self):
    '''Fails the subtest only if self.checked is True.'''
    if self.checked:
      self.ui.CallJSFunction('failSubTest')
      self.checked = False
