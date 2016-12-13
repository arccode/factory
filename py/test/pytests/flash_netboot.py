# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Runs flash_netboot to flash netboot firmware.

Note that it doesn't reboot after flashing firmware. Please run reboot
step after it.
"""

import logging
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.tools import flash_netboot
from cros.factory.utils.arg_utils import Arg

_TEST_TITLE = test_ui.MakeLabel('Flash Netboot Firmware', u'烧录 netboot 韧体')
_CSS = '#state {text-align:left;}'


class FlashNetbootTest(unittest.TestCase):
  ARGS = [
      Arg('image', str,
          'Path of netboot firmware image. Default to use '
          '/usr/local/factory/board/nv_image_*.bin',
          optional=True),
  ]

  def setUp(self):
    self._ui = test_ui.UI()
    self._template = ui_templates.OneScrollableSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._ui.AppendCSS(_CSS)

  def ShowResult(self, message):
    logging.info(message.strip())
    self._template.SetState(test_ui.Escape(message),
                            append=True, scroll_down=True)

  def runTest(self):
    self._ui.Run(blocking=False)

    netboot_flasher = flash_netboot.FlashNetboot(self.args.image,
                                                 on_output=self.ShowResult)
    self.ShowResult(netboot_flasher.WarningMessage())
    netboot_flasher.Run()
