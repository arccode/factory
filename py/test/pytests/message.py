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


class MessageTest(unittest.TestCase):
  ARGS = [
    Arg('html_en', str, 'Message (HTML in English).'),
    Arg('html_zh', str,' Message (HTML, in Chinese).', optional=True),
  ]

  def runTest(self):
    ui = UI(css='.message { font-size: 200% }')
    template = OneSection(ui)
    template.SetTitle(MakeLabel('Message', '讯息'))
    template.SetState(MakeLabel(self.args.html_en, self.args.html_zh,
                                'message'))
    ui.BindStandardKeys(bind_fail_keys=False)
    ui.Run()
