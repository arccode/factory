# -*- coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Uses HWID v3 to generate, encode, and verify the device's HWID."""

import os
import unittest

import factory_common # pylint: disable=W0611
from cros.factory import gooftool
from cros.factory import hwid
from cros.factory.event_log import Log
from cros.factory.gooftool import Gooftool
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg

# If present,  these files will override the board and probe results
# (for testing).
OVERRIDE_BOARD_PATH = os.path.join(
    hwid.DEFAULT_HWID_DATA_PATH,
    'OVERRIDE_BOARD')
OVERRIDE_PROBE_RESULTS_PATH = os.path.join(
    hwid.DEFAULT_HWID_DATA_PATH,
    'OVERRIDE_PROBE_RESULTS')


class HWIDV3Test(unittest.TestCase):
  ARGS = [
      Arg('generate', bool,
          'Generate and write the HWID (if False, only verify it).',
          True),
  ]

  def runTest(self):
    ui = test_ui.UI()
    template = ui_templates.OneSection(ui)
    shopfloor.update_local_hwid_data()

    if os.path.exists(OVERRIDE_BOARD_PATH):
      with open(OVERRIDE_BOARD_PATH) as f:
        board = f.read().strip()
    else:
      board = None

    template.SetState(test_ui.MakeLabel(
        'Probing components...',
        '正在探索零件...'))
    if os.path.exists(OVERRIDE_PROBE_RESULTS_PATH):
      with open(OVERRIDE_PROBE_RESULTS_PATH) as f:
        probe_results = f.read()
    else:
      probe_results = gooftool.probe.Probe()

    gt = Gooftool(hwid_version=3, board=board,
                  probe=lambda *args, **kwargs: probe_results)

    # Pass required device data entries for HWID generation/validation.
    device_data = dict(
        (k, v) for k, v in shopfloor.GetDeviceData().iteritems()
        if k in gt.db.shopfloor_device_info)

    if self.args.generate:
      template.SetState(test_ui.MakeLabel(
          'Generating HWID (v3)...',
          '正在产生 HWID (v3)...'))
      generated_hwid = gt.GenerateHwidV3(device_info=device_data)
      encoded_hwid = generated_hwid.encoded_string
      factory.console.info('Generated HWID: %s', encoded_hwid)
      Log('hwid', hwid=encoded_hwid)
    else:
      encoded_hwid = None

    template.SetState(test_ui.MakeLabel(
        'Verifying HWID (v3): %s...' % (
            encoded_hwid or '(unchanged)'),
        '正在验证 HWID (v3): %s...' % (
            encoded_hwid or '（不变）')))
    gt.VerifyHwidV3(encoded_hwid, probe_results)

    if self.args.generate:
      template.SetState(test_ui.MakeLabel(
          'Setting HWID (v3): %s...' % encoded_hwid,
          '正在写入 HWID (v3): %s...' % encoded_hwid))
      gt.WriteHWID(encoded_hwid)

