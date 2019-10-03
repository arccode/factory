# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test display functionailty.

Description
-----------
This test check basic display functionality by showing colors or images on
display, and ask operator to judge if the output looks correct.

The test can also be used to show an image for ``idle_timeout`` seconds, and
automatically pass itself after timeout is reached.

Test Procedure
--------------
If ``idle_timeout`` is set:

  1. An image is shown on the display.
  2. If the image looks incorrect, operator can press escape key or touch the
     display to fail the test.
  3. The test pass itself after ``idle_timeout`` seconds.

If ``idle_timeout`` is not set:

  1. A table of images to be tested is shown.
  2. Operator press space key to show the image.
  3. For each image, if it looks correct, operator press enter key to mark the
     item as passed, otherwise, operator press escape key to mark the item as
     failed.  Operator can also press space key or touch the display to return
     to the table view.
  4. The next image would be shown after the previous one is judged.
  5. The test is passed if all items are judged as passed, and fail if any item
     is judged as failed.

Dependency
----------
If ``items`` contains item with prefix ``image-``, external program ``bz2`` to
extract the compressed images.

Examples
--------
To test display functionality, add this into test list::

  {
    "pytest_name": "display"
  }

To test display functionality, show gray image, idle for an hour and pass, add
this into test list::

  {
    "pytest_name": "display",
    "args": {
      "items": ["solid-gray-127"],
      "idle_timeout": 3600
    }
  }

To test display functionality, and show some more images, add this into test
list::

  {
    "pytest_name": "display",
    "args": {
      "items": [
        "grid",
        "rectangle",
        "gradient-red",
        "image-complex",
        "image-black",
        "image-white",
        "image-crosstalk-black",
        "image-crosstalk-white",
        "image-gray-63",
        "image-gray-127",
        "image-gray-170",
        "image-horizontal-rgbw",
        "image-vertical-rgbw"
      ]
    }
  }
"""

import os

from cros.factory.test.i18n import _
from cros.factory.test.i18n import translation
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils


# The _() is necessary for pygettext to get translatable strings correctly.
_ALL_ITEMS = [
    _('solid-gray-170'),
    _('solid-gray-127'),
    _('solid-gray-63'),
    _('solid-red'),
    _('solid-green'),
    _('solid-blue'),
    _('solid-white'),
    _('solid-gray'),
    _('solid-black'),
    _('grid'),
    _('rectangle'),
    _('gradient-red'),
    _('gradient-green'),
    _('gradient-blue'),
    _('gradient-white'),
    _('image-complex'),
    _('image-black'),
    _('image-white'),
    _('image-crosstalk-black'),
    _('image-crosstalk-white'),
    _('image-gray-63'),
    _('image-gray-127'),
    _('image-gray-170'),
    _('image-horizontal-rgbw'),
    _('image-vertical-rgbw')
]
_ALL_ITEMS = [x[translation.DEFAULT_LOCALE] for x in _ALL_ITEMS]
_IMAGE_PREFIX = 'image-'


class DisplayTest(test_case.TestCase):
  """Tests the function of display.

  Properties:
    ui: test ui.
    checked: user has check the display of current subtest.
    fullscreen: the test ui is in fullscreen or not.
    static_dir: string of static file directory.
  """
  ARGS = [
      Arg('items', list,
          'Set items to be shown on screen. Available items are:\n%s\n' %
          '\n'.join('  * ``"%s"``' % x for x in _ALL_ITEMS),
          default=['solid-gray-170', 'solid-gray-127', 'solid-gray-63',
                   'solid-red', 'solid-green', 'solid-blue']),
      Arg('idle_timeout', int,
          'If given, the test would be start automatically, run for '
          'idle_timeout seconds, and pass itself. '
          'Note that items should contain exactly one item in this mode.',
          default=None),
      Arg('quick_display', bool,
          'If set to true, the next item will be shown automatically on '
          'enter pressed i.e. no additional space needed to toggle screen.',
          default=True)
  ]

  def setUp(self):
    """Initializes frontend presentation and properties."""
    self.static_dir = self.ui.GetStaticDirectoryPath()

    self.idle_timeout = self.args.idle_timeout
    if self.idle_timeout is not None and len(self.args.items) != 1:
      raise ValueError('items should have exactly one item in idle mode.')

    unknown_items = set(self.args.items) - set(_ALL_ITEMS)
    if unknown_items:
      raise ValueError('Unknown item %r in items.' % list(unknown_items))

    self.items = self.args.items
    self.images = [
        '%s.bmp' % item[len(_IMAGE_PREFIX):] for item in self.items
        if item.startswith(_IMAGE_PREFIX)
    ]
    if self.images:
      self.ExtractTestImages()
    self.frontend_proxy = self.ui.InitJSTestObject('DisplayTest', self.items)
    self.checked = False
    self.fullscreen = False

  def tearDown(self):
    self.RemoveTestImages()

  def runTest(self):
    """Sets the callback function of keys."""
    if self.idle_timeout is None:
      self.ui.BindKey(test_ui.SPACE_KEY, self.OnSpacePressed)
      self.ui.BindKey(test_ui.ENTER_KEY, self.OnEnterPressed)
      self.event_loop.AddEventHandler('onFullscreenClicked',
                                      self.OnSpacePressed)
      self.ui.HideElement('display-timer')
    else:
      # Automatically enter fullscreen mode in idle mode.
      self.ToggleFullscreen()
      self.event_loop.AddEventHandler('onFullscreenClicked', self.OnFailPressed)
      self.ui.StartCountdownTimer(self.idle_timeout, self.PassTask)
    self.ui.BindKey(test_ui.ESCAPE_KEY, self.OnFailPressed)
    self.WaitTaskEnd()

  def ExtractTestImages(self):
    """Extracts selected test images from test_images.tar.bz2."""
    file_utils.ExtractFile(os.path.join(self.static_dir, 'test_images.tar.bz2'),
                           self.static_dir, only_extracts=self.images)

  def RemoveTestImages(self):
    """Removes extracted image files after test finished."""
    for image in self.images:
      file_utils.TryUnlink(os.path.join(self.static_dir, image))

  def OnSpacePressed(self, event):
    """Sets self.checked to True. Calls JS function to switch display on/off."""
    del event  # Unused.
    self.ToggleFullscreen()

  def ToggleFullscreen(self):
    self.checked = True
    self.frontend_proxy.ToggleFullscreen()
    self.fullscreen = not self.fullscreen

  def OnEnterPressed(self, event):
    """Passes the subtest only if self.checked is True."""
    del event  # Unused.
    if self.checked:
      self.frontend_proxy.JudgeSubTest(True)
      # If the next subtest will be in fullscreen mode, checked should be True
      self.checked = self.fullscreen
      if self.args.quick_display and not self.fullscreen:
        self.ToggleFullscreen()

  def OnFailPressed(self, event):
    """Fails the subtest only if self.checked is True."""
    del event  # Unused.
    if self.checked:
      self.frontend_proxy.JudgeSubTest(False)
      # If the next subtest will be in fullscreen mode, checked should be True
      self.checked = self.fullscreen
