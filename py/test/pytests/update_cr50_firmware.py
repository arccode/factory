# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Update Cr50 firmware.

Description
-----------
This test calls `trunks_send` on DUT to update Cr50 firmware. The Cr50 firmware
image to update is either from a given path in station or from the release
partition on DUT.

`trunks_send` is a program with ability to update Cr50 firmware. Notice that
some older factory branches might have only `usb_updater` but no `trunks_send`.

To prepare Cr50 firmware image on station, download the release image with
desired Cr50 firmware image and find the image in DEFAULT_FIRMWARE_PATH below.

Test Procedure
--------------
This is an automatic test that doesn't need any user interaction.

1. Firstly, this test will create a DUT link.
2. If Cr50 firmware image source is from station, the image would be sent to
   DUT. Else, the release partition on DUT will be mounted.
3. DUT runs `trunks_send` to update Cr50 firmware.

Dependency
----------
- DUT link must be ready before running this test.
- `trunks_send` on DUT.
- Cr50 firmware image must be prepared.

Examples
--------
To update Cr50 firmware with the Cr50 firmware image in DUT release partition,
add this in test list::

  {
    "pytest_name": "update_cr50_firmware"
  }

To update Cr50 firmware with the Cr50 firmware image in station::

  {
    "pytest_name": "update_cr50_firmware",
    "args": {
      "firmware_file": "/path/on/station/to/cr50.bin.prod",
      "from_release": false
    }
  }
"""

import os

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sys_utils


TRUNKS_SEND = '/usr/sbin/trunks_send'
DEFAULT_FIRMWARE_PATH = '/opt/google/cr50/firmware/cr50.bin.prod'


class UpdateCr50FirmwareTest(test_ui.TestCaseWithUI):
  ARGS = [
      Arg('firmware_file', str, 'The full path of the firmware.',
          default=None),
      Arg('from_release', bool, 'Find the firmware from release rootfs.',
          default=True),
      Arg('force', bool, 'Force update',
          default=False),
  ]

  ui_class = test_ui.ScrollableLogUI

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def runTest(self):
    """Update Cr50 firmware."""
    if self.args.firmware_file is None:
      self.assertEqual(
          self.args.from_release, True,
          'Must set "from_release" to True if not specifiying firmware_file')
      self.args.firmware_file = DEFAULT_FIRMWARE_PATH

    self.assertEqual(self.args.firmware_file[0], '/',
                     'firmware_file should be a full path')

    if self.args.from_release:
      with sys_utils.MountPartition(
          self.dut.partitions.RELEASE_ROOTFS.path, dut=self.dut) as root:
        self._UpdateCr50Firmware(
            os.path.join(root, self.args.firmware_file[1:]))
    else:
      if self.dut.link.IsLocal():
        self._UpdateCr50Firmware(self.args.firmware_file)
      else:
        with self.dut.temp.TempFile() as dut_temp_file:
          self.dut.SendFile(self.args.firmware_file, dut_temp_file)
          self._UpdateCr50Firmware(dut_temp_file)

  def _UpdateCr50Firmware(self, firmware_file):
    if self.args.force:
      cmd = [TRUNKS_SEND, '--force', '--update', firmware_file]
    else:
      cmd = [TRUNKS_SEND, '--update', firmware_file]

    returncode = self.ui.PipeProcessOutputToUI(cmd)
    self.assertEqual(0, returncode,
                     'Cr50 firmware update failed: %d.' % returncode)
