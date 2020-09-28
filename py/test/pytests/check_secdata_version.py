# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""A factory test to check the secdata version.

Description
-----------
This test checks if the secdata version is the expected version.

According to platform/vboot_reference/firmware/2lib/include/2secdata_struct.h,
secdata version is an 8-bit integer defined as (major << 4 | minor << 0).

Test Procedure
--------------
This is an automatic test that doesn't need any user interaction.
Ideally the test should always pass. However, if the test fails, we need to
clear secdata and let the system regenerate it again. It can be done by

  - Re-enable cr50 factory mode (`gsctool -a -F enable`), or
  - Run `chromeos-tpm-recovery` by "(T) Reset TPM" action or "(R) Reset" action
    in a factory shim, depending on whether the device is finalized or not


Dependency
----------
- `tpmc`

Examples
--------
To verify that secdata version is 1.0::

  {
    "pytest_name": "check_secdata_version",
    "disable_services": [
      "trunksd"
    ],
    "args": {
      "major_version": 1,
      "minor_version": 0
    }
  }
"""

from cros.factory.device import device_utils
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg


class SecdataVersionTest(test_case.TestCase):
  """Checks the secdata version."""
  ARGS = [
      Arg('major_version', int, 'Major version of secdata.', default=1),
      Arg('minor_version', int, 'Minor version of secdata.', default=0)
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def runTest(self):
    out = int(self.dut.CallOutput(['tpmc', 'read', '0x1008', '1']), 16)
    expect = self.args.major_version << 4 | self.args.minor_version << 0
    self.assertEqual(out, expect, 'Secdata version is incorrect')
