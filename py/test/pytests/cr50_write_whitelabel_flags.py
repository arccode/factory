# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Write cr50 whitelabel flags if this is a whitelabel device.

Description
-----------
This test checks if current device is a whitelabel device.  If it is, the test
writes cr50 whitelabel flags to cr50 flash.  Otherwise, the test does nothing.

Test Procedure
--------------
1. Call `cros_config` to check if current device is a whitelabel device.
2. Log `is_whitelabel` and `whitelabel_tag`.
3. If `is_whitelabel`, call `gooftool cr50_write_whitelabel_flags`.

Dependency
----------
- DUT link must be ready.
- Command `cros_config` on DUT.
- Script `cr50-set-board-id.sh` needs to support
  `cr50-set-board-id.sh whitelabel_<pvt|dev>_flags`

Examples
--------
This test is added to SMTEnd test group by default.  If you want to place it at
different timing, add "Cr50WriteWhitelabelFlags" test item to your test group.
"""

import functools
import logging

from cros.factory.device import device_utils
from cros.factory.gooftool import common as gooftool_common
from cros.factory.gooftool import cros_config as cros_config_module
from cros.factory.test.utils import deploy_utils
from cros.factory.test import test_case
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg


class Cr50WriteWhitelabelFlags(test_case.TestCase):
  ARGS = [
      Arg('enable_zero_touch', bool, (
          'Enable zero touch enrollment.  This will set the cr50 SN bits using '
          'VPD field attested_device_id.'), default=False),
  ]

  def setUp(self):
    # Setups the DUT environments.
    self.dut = device_utils.CreateDUTInterface()
    dut_shell = functools.partial(gooftool_common.Shell, sys_interface=self.dut)
    self.cros_config = cros_config_module.CrosConfig(dut_shell)

  def runTest(self):
    is_whitelabel, whitelabel_tag = self.cros_config.GetWhiteLabelTag()

    testlog.LogParam('is_whitelabel', is_whitelabel)
    testlog.LogParam('whitelabel_tag', whitelabel_tag)

    if not is_whitelabel:
      return

    args = []
    if self.args.enable_zero_touch:
      args.append('--enable_zero_touch')

    factory_tools = deploy_utils.CreateFactoryTools(self.dut)
    try:
      factory_tools.CheckCall(
          ['gooftool', 'cr50_write_whitelabel_flags', *args])
    except Exception:
      logging.exception('Failed to set cr50 whitelabel flags.')
      raise
