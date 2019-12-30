# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Update Fingerprint MCU firmware.

Description
-----------
The FPMCU firmware image to update is either from a given path in the
station or on the DUT, or from the release partition on the DUT.

Test Procedure
--------------
This is an automatic test that doesn't need any user interaction.

1. Firstly, this test will create a DUT link.
2. If the FPMCU firmware image is from the station, the image would be sent
   to DUT.
3. If the FPMCU firmware image is not specified, the test mounts the release
   partition and get the FPMCU firmware image from there for update.

Dependency
----------
- DUT link must be ready before running this test.
- `flash_fp_mcu` (from ec-utils-test package) on DUT.
- `futility`, `crossystem`, and `cros_config` on DUT.
- FPMCU firmware image must be prepared.
- Hardware write-protection must be disabled (`crossystem wpsw_cur` returns 0).

Examples
--------
To update fingerprint firmware with the image in DUT release partition,
add this in test list::

  {
    "pytest_name": "update_fpmcu_firmware"
  }

To update fingerprint firmware with a specified image in the station
(only recommended in pre-PVT stages)::

  {
    "pytest_name": "update_fpmcu_firmware",
    "args": {
      "firmware_file": "/path/on/station/to/image.bin"
    }
  }
"""

import logging

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test.utils import fpmcu_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sys_utils
from cros.factory.utils.type_utils import Error

FLASHTOOL = '/usr/local/bin/flash_fp_mcu'
FPMCU_FW_DIR_UNDER_ROOTFS = 'opt/google/biod/fw'


class UpdateFpmcuFirmwareTest(test_case.TestCase):
  ARGS = [
      Arg('firmware_file', str, 'The full path of the firmware binary file.',
          default=None)
  ]

  ui_class = test_ui.ScrollableLogUI

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._fpmcu = fpmcu_utils.FpmcuDevice(self._dut)

  def runTest(self):
    # Before updating FPMCU firmware, HWWP must be disabled.
    if self._dut.CallOutput(['crossystem', 'wpsw_cur']).strip() != '0':
      raise Error('Hardware write protection is enabled.')

    fpmcu_board = self._dut.CallOutput(
        ['cros_config', '/fingerprint', 'board'])
    if not fpmcu_board:
      raise Error('No fingerprint board found in cros_config')

    if not self.args.firmware_file:
      logging.info('No specified path to FPMCU FW image')
      logging.info('Get FPMCU FW image from the release rootfs partition.')

      with sys_utils.MountPartition(
          self._dut.partitions.RELEASE_ROOTFS.path, dut=self._dut) as root:
        pattern = self._dut.path.join(root, FPMCU_FW_DIR_UNDER_ROOTFS,
                                      '%s_v*.bin' % fpmcu_board)
        fpmcu_fw_files = self._dut.Glob(pattern)
        self.assertEqual(len(fpmcu_fw_files), 1,
                         'No uniquely matched FPMCU firmware blob found')
        self.UpdateFpmcuFirmware(fpmcu_fw_files[0])
    else:
      self.assertEqual(self.args.firmware_file[0], '/',
                       'firmware_file should be a full path')
      if self._dut.link.IsLocal():
        self.UpdateFpmcuFirmware(self.args.firmware_file)
      else:
        with self._dut.temp.TempFile() as dut_temp_file:
          self._dut.SendFile(self.args.firmware_file, dut_temp_file)
          self.UpdateFpmcuFirmware(dut_temp_file)

  def UpdateFpmcuFirmware(self, firmware_file):
    """Update FPMCU firmware by `flash_fp_mcu`."""
    flash_cmd = [FLASHTOOL, firmware_file]
    old_ro_ver, old_rw_ver = self._fpmcu.GetFpmcuFirmwareVersion()
    bin_ro_ver, bin_rw_ver = self.GetFirmwareVersionFromFile(firmware_file)

    logging.info('Current FPMCU RO: %s, RW: %s', old_ro_ver, old_rw_ver)
    logging.info('Ready to update FPMCU firmware to RO: %s, RW: %s.',
                 bin_ro_ver, bin_rw_ver)

    session.console.debug(self._dut.CallOutput(flash_cmd))
    new_ro_ver, new_rw_ver = self._fpmcu.GetFpmcuFirmwareVersion()

    self.assertEqual(new_ro_ver, bin_ro_ver,
                     'New FPMCU RO: %s does not match the expected RO: %s.'
                     % (new_rw_ver, bin_ro_ver))
    self.assertEqual(new_rw_ver, bin_rw_ver,
                     'New FPMCU RW: %s does not match the expected RW: %s.'
                     % (new_rw_ver, bin_rw_ver))

  def GetFirmwareVersionFromFile(self, firmware_file):
    """Read RO and RW FW version from the FW binary file."""
    ro_ver = self.ReadFmapArea(firmware_file, "RO_FRID")
    rw_ver = self.ReadFmapArea(firmware_file, "RW_FWID")
    return (ro_ver, rw_ver)

  def ReadFmapArea(self, firmware_file, area_name):
    """Read fmap from a specified area_name."""
    get_fmap_cmd = ["futility", "dump_fmap", "-p", firmware_file, area_name]
    get_fmap_output = self._dut.CheckOutput(get_fmap_cmd)
    if not get_fmap_output:
      raise Error('Fmap area name might be wrong?')
    unused_name, offset, size = get_fmap_output.split()
    get_ro_ver_cmd = ["dd", "bs=1", "skip=%s" % offset,
                      "count=%s" % size, "if=%s" % firmware_file]
    return self._dut.CheckOutput(get_ro_ver_cmd).strip('\x00')
