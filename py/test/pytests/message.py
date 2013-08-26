# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Displays a message.

The operator can press the space or enter key to proceed.
"""


import unittest


from cros.factory.test.args import Arg
from cros.factory.test.test_ui import MakeLabel, UI
from cros.factory.test.ui_templates import OneSection


CSS_TEMPLATE = """
.message { font-size: %(text_size)s%%; color: %(text_color)s; }
.state { background-color: %(background_color)s; }
"""


class MessageTest(unittest.TestCase):
  ARGS = [
    Arg('html_en', str, 'Message (HTML in English).'),
    Arg('html_zh', str,' Message (HTML, in Chinese).', optional=True),
    Arg('text_size', str, 'size of message in percentage', default='200'),
    Arg('text_color', str, 'color of message (in CSS)', default='black'),
    Arg('background_color', str, 'background color (in CSS)', default='white')
  ]

  def runTest(self):
    css = (CSS_TEMPLATE %
        dict(text_size=self.args.text_size,
             text_color=self.args.text_color,
             background_color=self.args.background_color))
    ui = UI(css=css)
    template = OneSection(ui)
    template.SetTitle(MakeLabel('Message', '讯息'))
    template.SetState(
        '<div class="state">' +
        MakeLabel(self.args.html_en, self.args.html_zh, 'message') +
        '</div>')
    ui.BindStandardKeys(bind_fail_keys=False)
    ui.Run()
