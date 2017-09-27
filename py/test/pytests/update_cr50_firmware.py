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
desired Cr50 firmware image and find the image in FIRMWARE_RELATIVE_PATH below.

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

import logging
import os
import subprocess
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sys_utils

_CSS = '#state { text-align: left; }'

TRUNKS_SEND = '/usr/sbin/trunks_send'
FIRMWARE_RELATIVE_PATH = 'opt/google/cr50/firmware/cr50.bin.prod'


class UpdateCr50FirmwareTest(unittest.TestCase):
  ARGS = [
      Arg('firmware_file', str, 'The full path of the firmware.',
          optional=True),
      Arg('from_release', bool, 'Find the firmware from release rootfs.',
          optional=True, default=True)
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self._ui = test_ui.UI()
    self._template = ui_templates.OneScrollableSection(self._ui)
    self._ui.AppendCSS(_CSS)

  def UpdateCr50Firmware(self):
    """Update Cr50 firmware."""
    self.assertEqual(
        1, len(filter(None, [self.args.firmware_file, self.args.from_release])),
        'Must specify exactly one of "firmware_file" or "from_release".')
    if self.args.firmware_file:
      if self.dut.link.IsLocal():
        self._UpdateCr50Firmware(self.args.firmware_file)
      else:
        with self.dut.temp.TempFile() as dut_temp_file:
          self.dut.SendFile(self.args.firmware_file, dut_temp_file)
          self._UpdateCr50Firmware(dut_temp_file)
    elif self.args.from_release:
      with sys_utils.MountPartition(
          self.dut.partitions.RELEASE_ROOTFS.path, dut=self.dut) as root:
        firmware_path = os.path.join(root, FIRMWARE_RELATIVE_PATH)
        self._UpdateCr50Firmware(firmware_path)

  def _UpdateCr50Firmware(self, firmware_file):
    p = self.dut.Popen(
        [TRUNKS_SEND, '--update', firmware_file],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, log=True)

    for line in iter(p.stdout.readline, ''):
      logging.info(line.strip())
      self._template.SetState(test_ui.Escape(line), append=True)

    if p.poll() != 0:
      self._ui.Fail('Cr50 firmware update failed: %d.' % p.returncode)
    else:
      self._ui.Pass()

  def runTest(self):
    self._ui.RunInBackground(self.UpdateCr50Firmware)
    self._ui.Run()
