# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to test the function of display."""

import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils

_ID_CONTAINER = 'display-test-container'

# The style is in display.css
# The layout contains one div for display.
_HTML_DISPLAY = (
    '<link rel="stylesheet" type="text/css" href="display.css">'
    '<div id="%s"></div>\n' % _ID_CONTAINER)


class DisplayTest(unittest.TestCase):
  """Tests the function of display.

  Properties:
    ui: test ui.
    template: ui template handling html layout.
    checked: user has check the display of current subtest.
    fullscreen: the test ui is in fullscreen or not.
    static_dir: string of static file directory.
  """
  ARGS = [
      Arg('colors', list,
          'Set colors. Available colors are\n'
          '        "solid-gray-170",\n'
          '        "solid-gray-127",\n'
          '        "solid-gray-63",\n'
          '        "solid-red",\n'
          '        "solid-green",\n'
          '        "solid-blue",\n'
          '        "solid-white",\n'
          '        "solid-gray",\n'
          '        "solid-black",\n'
          '        "grid",\n'
          '        "rectangle",\n'
          '        "gradient-red",\n'
          '        "gradient-green",\n'
          '        "gradient-blue",\n'
          '        "gradient-white"',
          default=['solid-gray-170', 'solid-gray-127', 'solid-gray-63',
                   'solid-red', 'solid-green', 'solid-blue'],
          optional=True),
      Arg('images', list,
          'Set customized images. Available images are\n'
          '        "complex.bmp",\n'
          '        "BLACK.BMP",\n'
          '        "WHITE.BMP",\n'
          '        "CrossTalk(black).bmp",\n'
          '        "CrossTalk(white).bmp",\n'
          '        "gray(63).bmp",\n'
          '        "gray(127).bmp",\n'
          '        "gray(170).bmp",\n'
          '        "Horizontal(RGBW).bmp",\n'
          '        "Vertical(RGBW).bmp"\n',
          default=[],
          optional=True),
  ]

  def setUp(self):
    """Initializes frontend presentation and properties."""
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendHTML(_HTML_DISPLAY)
    self.static_dir = self.FindFileStaticDirectory()
    if self.args.images:
      for image in self.args.images:
        self.args.colors.append('image-%s' % image)
      self.ExtractTestImages()
    self.ui.CallJSFunction('setupDisplayTest', _ID_CONTAINER, self.args.colors)
    self.checked = False
    self.fullscreen = False

  def tearDown(self):
    self.RemoveTestImages()
    return

  def runTest(self):
    """Sets the callback function of keys and run the test."""
    self.ui.BindKey(test_ui.SPACE_KEY, self.OnSpacePressed)
    self.ui.BindKey(test_ui.ENTER_KEY, self.OnEnterPressed)
    self.ui.BindKey(test_ui.ESCAPE_KEY, self.OnFailPressed)
    self.ui.AddEventHandler('OnSpacePressed', self.OnSpacePressed)
    self.ui.Run()

  def FindFileStaticDirectory(self):
    """Finds static file directory.

    Returns:
      String of static file directory
    """
    file_path = os.path.realpath(__file__)
    file_dir, file_name = os.path.split(file_path)
    file_static_dir = os.path.join(file_dir,
                                   os.path.splitext(file_name)[0] + '_static')
    return file_static_dir

  def ExtractTestImages(self):
    """Extracts selected test images from test_images.tar.gz."""
    file_utils.ExtractFile(os.path.join(self.static_dir, 'test_images.tar.gz'),
                           self.static_dir, self.args.images)

  def RemoveTestImages(self):
    """Removes extracted image files after test finished."""
    for image in self.args.images:
      file_utils.TryUnlink(os.path.join(self.static_dir, image))

  def OnSpacePressed(self, event):
    """Sets self.checked to True.Calls JS function to switch display on/off."""
    del event  # Unused.
    self.checked = True
    self.ui.CallJSFunction('switchDisplayOnOff')
    self.fullscreen = not self.fullscreen
    self.ui.HideTooltips()

  def OnEnterPressed(self, event):
    """Passes the subtest only if self.checked is True."""
    del event  # Unused.
    if self.checked:
      self.ui.CallJSFunction('passSubTest')
      # If the next subtest will be in fullscreen mode, checked should be True
      self.checked = self.fullscreen

  def OnFailPressed(self, event):
    """Fails the subtest only if self.checked is True."""
    del event  # Unused.
    if self.checked:
      self.ui.CallJSFunction('failSubTest')
      # If the next subtest will be in fullscreen mode, checked should be True
      self.checked = self.fullscreen
