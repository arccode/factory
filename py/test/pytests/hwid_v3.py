# -*- coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Uses HWID v3 to generate, encode, and verify the device's HWID."""

import logging
import os
import unittest
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.test.event_log import Log
from cros.factory.gooftool import probe
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.test import factory
from cros.factory.test import phase
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg

# If present,  these files will override the board and probe results
# (for testing).
OVERRIDE_BOARD_PATH = os.path.join(
    common.DEFAULT_HWID_DATA_PATH,
    'OVERRIDE_BOARD')
# OVERRIDE_PROBED_RESULTS should be generated with:
#    `gootool probe --include_vpd`
# to include all the VPD in it.
OVERRIDE_PROBED_RESULTS_PATH = os.path.join(
    common.DEFAULT_HWID_DATA_PATH,
    'OVERRIDE_PROBED_RESULTS')


class HWIDV3Test(unittest.TestCase):
  """A test for generating and verifying HWID v3."""
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
          default=False, optional=True),
      Arg('verify_checksum', bool,
          'Enable database checksum verification.', default=True, optional=True)
  ]

  def runTest(self):
    ui = test_ui.UI()
    template = ui_templates.OneSection(ui)

    phase.AssertStartingAtPhase(
        phase.EVT,
        self.args.verify_checksum,
        'HWID checksum must be verified')

    if not self.args.skip_shopfloor:
      shopfloor.update_local_hwid_data()

    template.SetState(test_ui.MakeLabel(
        'Probing components...',
        '正在探索零件...'))
    if os.path.exists(OVERRIDE_PROBED_RESULTS_PATH):
      with open(OVERRIDE_PROBED_RESULTS_PATH) as f:
        probed_results = yaml.load(f.read())
    else:
      probed_results = yaml.load(probe.Probe(probe_vpd=True).Encode())
    Log('probe', probe_results=probed_results)

    if os.path.exists(OVERRIDE_BOARD_PATH):
      with open(OVERRIDE_BOARD_PATH) as f:
        board = f.read().strip()
    else:
      board = common.ProbeBoard()

    hwdb = database.Database.LoadFile(
        os.path.join(common.DEFAULT_HWID_DATA_PATH, board.upper()),
        verify_checksum=self.args.verify_checksum)
    device_info = hwid_utils.GetDeviceInfo()
    vpd = hwid_utils.GetVPD(probed_results)

    if self.args.generate:
      template.SetState(test_ui.MakeLabel(
          'Generating HWID (v3)...',
          '正在产生 HWID (v3)...'))
      generated_hwid = hwid_utils.GenerateHWID(hwdb, probed_results,
                                               device_info, vpd,
                                               rma_mode=self.args.rma_mode)

      encoded_string = generated_hwid.encoded_string
      factory.console.info('Generated HWID: %s', encoded_string)
      decoded_hwid = hwid_utils.DecodeHWID(hwdb, encoded_string)
      logging.info('HWDB checksum: %s', hwdb.checksum)
      Log('hwid', hwid=encoded_string,
          hwdb_checksum=hwdb.checksum,
          components=hwid_utils.ParseDecodedHWID(decoded_hwid))
      shopfloor.UpdateDeviceData({'hwid': encoded_string})
    else:
      encoded_string = hwid_utils.GetHWIDString()

    template.SetState(test_ui.MakeLabel(
        'Verifying HWID (v3): %s...' % (
            encoded_string or '(unchanged)'),
        '正在验证 HWID (v3): %s...' % (
            encoded_string or '（不变）')))
    hwid_utils.VerifyHWID(hwdb, encoded_string, probed_results, vpd,
                          rma_mode=self.args.rma_mode)
    Log('hwid_verified', hwid=encoded_string,
        hwdb_checksum=hwdb.checksum)

    if self.args.generate:
      template.SetState(test_ui.MakeLabel(
          'Setting HWID (v3): %s...' % encoded_string,
          '正在写入 HWID (v3): %s...' % encoded_string))
      hwid_utils.WriteHWID(encoded_string)
