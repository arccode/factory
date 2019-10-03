# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Check firmware version of PD (TCPC) chip equal to or larger than minimum
version noted in corresponding EC driver.

Description
-----------
Some PD chip might have issues which need to be solved by the cooperation
between firmware of PD chip and corresponding EC driver. In order to make sure
PD chips are shipped with correct firmware version, this test asks two info from
EC via ectool; one is current firmware version and the other is the minimum
required firmware version. Then these two versions would be compared to confirm
firmware version in the PD chip is greater then or equal to minimum required
version.

Test Procedure
--------------
This is an automatic test that doesn't need any user interaction.

Dependency
----------
- DUT link must be ready before running this test.
- ``ectool`` utility.

Examples
--------
To verify PD chip in the port 0, add this in test list::

  {
    "pytest_name": "pd_fw_min_version"
  }

To verify multiple PD chips (ex: port 0 and 1), add this in test list::

  {
    "pytest_name": "pd_fw_min_version",
    "args": {
      "ports": [0, 1]
    }
  }

"""

import logging
import re
import unittest

from cros.factory.device import device_utils
from cros.factory.utils.arg_utils import Arg


class PdFwMinVersion(unittest.TestCase):

  ARGS = [
      Arg('ports', (int, list), 'Specify which PD ports are checked.',
          default=0)]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def runTest(self):
    if isinstance(self.args.ports, int):
      self.args.ports = [self.args.ports]

    for port in self.args.ports:
      info = self.dut.CheckOutput(['ectool', 'pdchipinfo', '%s' % port],
                                  log=True)
      logging.info('pdchipinfo of port %d:\n%s.', port, info)
      res = re.search(r'^min_req_fw_version: (0x\w+)$', info, re.MULTILINE)
      if not res:
        raise ValueError('ectool or ec firmware does not support to query '
                         'minimum required version of TCPC firmware.')
      min_fw_version = res.group(1)

      res = re.search(r'^fw_version: (0x\w+)$', info, re.MULTILINE)
      if not res:
        raise ValueError('The EC driver of the TCPC chip does not provide '
                         'firmware version.')
      fw_version = res.group(1)

      self.assertTrue(int(fw_version, 16) >= int(min_fw_version, 16),
                      'TCPC firmware version (%s) is less then minimum '
                      'required one (%s).' % (fw_version, min_fw_version))
