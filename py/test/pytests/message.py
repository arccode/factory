# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Displays a message.

Description
-----------
This test displays a HTML message to the operator, and wait for the operator
pressing space key to pass the test.

If ``manual_check`` is True, the operator can also press escape key to fail the
test.

If ``seconds`` is given, the test would pass automatically after ``seconds``
seconds.

Test Procedure
--------------
When started, the test will show a message and wait for operator to press space
to pass the test, or press escape to fail the test (if ``manual_check`` is set).

Dependency
----------
None.

Examples
--------
To show a message, add this in test list::

  {
    "pytest_name": "message",
    "args": {
      "html": "i18n! Hello world!"
    }
  }

To show a message with some formatting, and give operator ability to fail the
test::

  {
    "pytest_name": "message",
    "args": {
      "text_size": 300,
      "manual_check": true,
      "show_press_button_hint": true,
      "html": "i18n! Please check if the result is <b>correct</b>.",
      "text_color": "red"
    }
  }

To show a message for 20 seconds, and automatically pass::

  {
    "pytest_name": "message",
    "args": {
      "seconds": 20,
      "html": "i18n! Waiting for something..."
    }
  }
"""

from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg


CSS_TEMPLATE = """
.message { font-size: %(text_size)s%%; color: %(text_color)s; }
test-template { --template-background-color: %(background_color)s; }
"""


class MessageTest(test_case.TestCase):
  """A factory test to display a message."""
  ARGS = [
      i18n_arg_utils.I18nArg('html', 'Message in HTML'),
      Arg('text_size', str, 'size of message in percentage', default='200'),
      Arg('text_color', str, 'color of message (in CSS)', default='black'),
      Arg('background_color', str, 'background color (in CSS)',
          default='white'),
      Arg('seconds', int, 'duration to display message. '
          'Specify None to show until key press.',
          default=None),
      Arg('manual_check', bool, 'If set to true, operator can press ESC to '
          'fail the test case.', default=False),
      Arg('show_press_button_hint', bool, 'If set to true, will show '
          'addition message to ask operators to press the button.',
          default=False)
  ]

  def setUp(self):
    css = (CSS_TEMPLATE %
           dict(text_size=self.args.text_size,
                text_color=self.args.text_color,
                background_color=self.args.background_color))
    self.ui.AppendCSS(css)

    press_button_hint = ''
    if self.args.show_press_button_hint:
      if self.args.manual_check:
        press_button_hint = _(
            '<div>Press <strong>Enter</strong> to continue, '
            'or <strong>ESC</strong> if things are not going right.</div>')
      else:
        press_button_hint = _(
            '<div>Press <strong>Enter</strong> to continue.</div>')

    self.ui.SetState([
        '<span class="message">', self.args.html, '</span>', press_button_hint
    ])

    self.ui.BindStandardPassKeys()
    if self.args.manual_check:
      self.ui.BindStandardFailKeys()

  def runTest(self):
    if self.args.seconds:
      self.ui.StartCountdownTimer(self.args.seconds, self.PassTask)
    self.WaitTaskEnd()
