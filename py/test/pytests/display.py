# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to test the function of display."""

import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import countdown_timer
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils


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
                   'solid-red', 'solid-green', 'solid-blue']),
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
          default=[]),
      Arg('idle_timeout', int,
          'If given, the test would be start automatically, run for '
          'idle_timeout seconds, and pass itself. '
          'Note that colors and images should contain exactly one item total '
          'in this mode.', default=None)
  ]

  def setUp(self):
    """Initializes frontend presentation and properties."""
    self.ui = test_ui.UI()
    self.ui.AppendCSSLink('display.css')
    self.template = ui_templates.OneSection(self.ui)
    self.static_dir = self.FindFileStaticDirectory()

    self.idle_timeout = self.args.idle_timeout
    if (self.idle_timeout is not None and
        len(self.args.colors) + len(self.args.images) != 1):
      raise ValueError(
          'colors and images should have exactly one item total in idle mode.')

    if self.args.images:
      for image in self.args.images:
        self.args.colors.append('image-%s' % image)
      self.ExtractTestImages()
    self.ui.CallJSFunction(
        'setupDisplayTest', ui_templates.STATE_ID, self.args.colors)
    self.checked = False
    self.fullscreen = False

  def tearDown(self):
    self.RemoveTestImages()

  def runTest(self):
    """Sets the callback function of keys and run the test."""
    if self.idle_timeout is None:
      self.ui.BindKey(test_ui.SPACE_KEY, self.OnSpacePressed)
      self.ui.BindKey(test_ui.ENTER_KEY, self.OnEnterPressed)
      self.ui.AddEventHandler('OnFullscreenClicked', self.OnSpacePressed)
    else:
      # Automatically enter fullscreen mode in idle mode.
      self.ToggleFullscreen()
      self.ui.AddEventHandler('OnFullscreenClicked', self.OnFailPressed)
      countdown_timer.StartCountdownTimer(self.idle_timeout, self.ui.Pass,
                                          self.ui, [])
    self.ui.BindKey(test_ui.ESCAPE_KEY, self.OnFailPressed)
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
    """Sets self.checked to True. Calls JS function to switch display on/off."""
    del event  # Unused.
    self.ToggleFullscreen()

  def ToggleFullscreen(self):
    self.checked = True
    self.ui.CallJSFunction('switchDisplayOnOff')
    self.fullscreen = not self.fullscreen

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
