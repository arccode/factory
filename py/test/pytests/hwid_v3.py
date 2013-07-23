# -*- coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Uses HWID v3 to generate, encode, and verify the device's HWID."""

import os
import unittest

import factory_common # pylint: disable=W0611
from cros.factory.event_log import Log
from cros.factory.gooftool import probe, gooftool
from cros.factory.gooftool import Gooftool
from cros.factory.hwdb.hwid_tool import ProbeResults  # pylint: disable=E0611
from cros.factory.hwid import common
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg

# If present,  these files will override the board and probe results
# (for testing).
OVERRIDE_BOARD_PATH = os.path.join(
    common.DEFAULT_HWID_DATA_PATH,
    'OVERRIDE_BOARD')
OVERRIDE_PROBE_RESULTS_PATH = os.path.join(
    common.DEFAULT_HWID_DATA_PATH,
    'OVERRIDE_PROBE_RESULTS')


class HWIDV3Test(unittest.TestCase):
  ARGS = [
    Arg('generate', bool,
        'Generate and write the HWID (if False, only verify it).',
        True),
    Arg('skip_shopfloor', bool,
        'Set this value to True to skip updating hwid data from shopfloor '
        'server.',
        default=False, optional=True),
    Arg('rma_mode', bool,
        'Enable rma_mode, do not check for deprecated components.',
        default=False, optional=True)
  ]

  def runTest(self):
    ui = test_ui.UI()
    template = ui_templates.OneSection(ui)
    if not self.args.skip_shopfloor:
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
        probe_results = ProbeResults.Decode(f.read())
    else:
      probe_results = probe.Probe()
    Log('probe', probe_results=probe_results)

    gt = Gooftool(hwid_version=3, board=board,
                  probe=lambda *args, **kwargs: probe_results)

    device_data = shopfloor.GetDeviceData()

    if self.args.generate:
      template.SetState(test_ui.MakeLabel(
          'Generating HWID (v3)...',
          '正在产生 HWID (v3)...'))
      generated_hwid = gt.GenerateHwidV3(device_info=device_data,
                                         rma_mode=self.args.rma_mode)
      hwid = generated_hwid.encoded_string
      factory.console.info('Generated HWID: %s', hwid)
      decoded_hwid = gt.DecodeHwidV3(hwid)
      Log('hwid', hwid=hwid, components=gooftool.ParseDecodedHWID(decoded_hwid))
      shopfloor.UpdateDeviceData({'hwid': hwid})
    else:
      hwid = None

    template.SetState(test_ui.MakeLabel(
        'Verifying HWID (v3): %s...' % (
            hwid or '(unchanged)'),
        '正在验证 HWID (v3): %s...' % (
            hwid or '（不变）')))
    gt.VerifyHwidV3(hwid, probe_results)

    if self.args.generate:
      template.SetState(test_ui.MakeLabel(
          'Setting HWID (v3): %s...' % hwid,
          '正在写入 HWID (v3): %s...' % hwid))
      gt.WriteHWID(hwid)

