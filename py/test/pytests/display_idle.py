# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to test the function of display.
"""

import logging
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils

_ID_CONTAINER = 'display-test-container'

# The style is in display.css
# The layout contains one div for display.
_HTML_DISPLAY = (
    '<link rel="stylesheet" type="text/css" href="display_idle.css">'
    '<div id="%s"></div>\n' % _ID_CONTAINER)


class DisplayIdleTest(unittest.TestCase):
  """Tests the function of display.

  Properties:
    ui: test ui.
    template: ui template handling html layout.
    checked: user has check the display of current subtest.
    fullscreen: the test ui is in fullscreen or not.
  """

  ARGS = [
      Arg('timeout_secs', int, 'Timeout for the test.', default=20),
      Arg('start_without_prompt', int, 'Start the test without prompt',
          default=False),
  ]

  def setUp(self):
    """Initializes frontend presentation and properties."""
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendHTML(_HTML_DISPLAY)
    self.ui.CallJSFunction('setupDisplayTest', _ID_CONTAINER)
    self.checked = False
    self.fullscreen = False

  def tearDown(self):
    return

  def CountdownTimer(self):
    """Starts a countdown timer and passes the test if timer reaches zero."""
    logging.info('Start countdown timer for %s seconds',
                 self.args.timeout_secs)
    time.sleep(self.args.timeout_secs)
    logging.info('Time is up, operator did not see any failure')
    self.ui.Pass()

  def runTest(self):
    """Sets the callback function of keys and run the test."""
    self.ui.BindKey(test_ui.SPACE_KEY, self.OnSpacePressed)
    self.ui.BindKey(test_ui.ESCAPE_KEY, self.OnFailPressed)
    if self.args.start_without_prompt:
      self.OnSpacePressed(None)
    self.ui.AddEventHandler('OnSpacePressed', self.OnSpacePressed)
    self.ui.Run()

  def OnSpacePressed(self, event):
    """Sets self.checked to True.Calls JS function to switch display on/off.

    Also, set countdown timer once operator press space for the first time.
    """
    del event  # Unused.
    if not self.checked:
      self.checked = True
      process_utils.StartDaemonThread(target=self.CountdownTimer)
    self.ui.CallJSFunction('switchDisplayOnOff')
    self.fullscreen = not self.fullscreen

  def OnFailPressed(self, event):
    """Fails the subtest only if self.checked is True."""
    del event  # Unused.
    if self.checked:
      self.ui.CallJSFunction('failSubTest')
      # If the next subtest will be in fullscreen mode, checked should be True
      self.checked = self.fullscreen
