# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Update Fingerprint MCU firmware.

Description
-----------
This test provides two modes, `update mode` and `check mode`. Mode is
specified by the test argument ``method``.

1. In `update mode`, the test runs `flash_fp_mcu` to update the current
   fingerprint firmware.
2. In `check mode`, the test checks if the fingerprint firmware version
   of the DUT is equal to the given version.

The FPMCU firmware image updates/checks either from a given path in the
station or on the DUT, or from the release partition on the DUT.

Test Procedure
--------------
This is an automatic test that doesn't need any user interaction.

1. Firstly, this test will create a DUT link.
2. If the FPMCU firmware image is from the station, the image would be sent
   to DUT.
3. If the FPMCU firmware image is not specified, the test mounts the release
   partition and gets the FPMCU firmware image from there.
4. If `method` is set to `UPDATE`, DUT runs `flash_fp_mcu` to update the
   fingerprint firmware using the specified image.
5. If `method` is set to `CHECK_VERSION`, DUT compares the version of the
   current fingerprint firmware and the version of the specified image.

Dependency
----------
- DUT link must be ready before running this test.
- `flash_fp_mcu` (from ec-utils-test package) on DUT.
- `futility`, `crossystem`, and `cros_config` on DUT.
- FPMCU firmware image must be prepared.
- Hardware write-protection must be disabled (`crossystem wpsw_cur` returns 0).

Examples
--------
To update the fingerprint firmware with the image in DUT release partition,
add this in test list::

  {
    "pytest_name": "update_fpmcu_firmware"
  }

To update the fingerprint firmware with a specified image in the station
(only recommended in pre-PVT stages)::

  {
    "pytest_name": "update_fpmcu_firmware",
    "args": {
      "method": "UPDATE"
      "firmware_file": "/path/on/station/to/image.bin"
    }
  }

To check if the fingerprint firmware version is equal to the version in the
release image::

  {
    "pytest_name": "update_fpmcu_firmware",
    "args": {
      "method": "CHECK_VERSION"
    }
  }
"""

import logging

from cros.factory.device import device_utils
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test.utils import fpmcu_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sys_utils
from cros.factory.utils.type_utils import Enum
from cros.factory.utils.type_utils import Error

FLASHTOOL = '/usr/local/bin/flash_fp_mcu'
FPMCU_FW_DIR_UNDER_ROOTFS = 'opt/google/biod/fw'


class UpdateFpmcuFirmwareTest(test_case.TestCase):
  _METHOD_TYPE = Enum(['UPDATE', 'CHECK_VERSION'])

  ARGS = [
      Arg('firmware_file', str, 'The full path of the firmware binary file.',
          default=None),
      Arg(
          'method', _METHOD_TYPE,
          'Specify whether to update the fingerprint firmware or to check the '
          'fingerprint firmware version.', default=_METHOD_TYPE.UPDATE),
  ]

  ui_class = test_ui.ScrollableLogUI

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._fpmcu = fpmcu_utils.FpmcuDevice(self._dut)

  def runTest(self):
    if self.args.method == self._METHOD_TYPE.UPDATE:
      method_func = self.UpdateFpmcuFirmware
    else:
      method_func = self.CheckFpmcuFirmwareVersion

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
        method_func(fpmcu_fw_files[0])
    else:
      self.assertEqual(self.args.firmware_file[0], '/',
                       'firmware_file should be a full path')
      if self._dut.link.IsLocal():
        method_func(self.args.firmware_file)
      else:
        with self._dut.temp.TempFile() as dut_temp_file:
          self._dut.SendFile(self.args.firmware_file, dut_temp_file)
          method_func(dut_temp_file)

  def UpdateFpmcuFirmware(self, firmware_file):
    """Update FPMCU firmware by `flash_fp_mcu`.

    Before updating FPMCU firmware, HWWP must be disabled.
    """
    if self._dut.CallOutput(['crossystem', 'wpsw_cur']).strip() != '0':
      raise Error('Hardware write protection is enabled.')

    # Log current and expected firmware version.
    _, _, _, _ = self.GetCurrentAndExpectedFirmwareVersion(firmware_file)

    flash_cmd = [FLASHTOOL, firmware_file]

    session.console.debug(self._dut.CallOutput(flash_cmd))

  def CheckFpmcuFirmwareVersion(self, firmware_file):
    cur_ro_ver, cur_rw_ver, bin_ro_ver, bin_rw_ver = \
      self.GetCurrentAndExpectedFirmwareVersion(firmware_file)

    self.assertEqual(
        cur_ro_ver, bin_ro_ver,
        'Current FPMCU RO: %s does not match the expected RO: %s.' %
        (cur_rw_ver, bin_ro_ver))
    self.assertEqual(
        cur_rw_ver, bin_rw_ver,
        'Current FPMCU RW: %s does not match the expected RW: %s.' %
        (cur_rw_ver, bin_rw_ver))

  def GetCurrentAndExpectedFirmwareVersion(self, firmware_file):
    cur_ro_ver = cur_rw_ver = ''
    try:
      cur_ro_ver, cur_rw_ver = self._fpmcu.GetFpmcuFirmwareVersion()
      logging.info('Current FPMCU RO: %s, RW: %s', cur_ro_ver, cur_rw_ver)
    except Exception:
      logging.exception('Fail to read the current FPMCU RO/RW FW versions.')

    bin_ro_ver, bin_rw_ver = self.GetFirmwareVersionFromFile(firmware_file)
    logging.info('Expected FPMCU RO: %s, RW: %s.', bin_ro_ver, bin_rw_ver)

    return (cur_ro_ver, cur_rw_ver, bin_ro_ver, bin_rw_ver)

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
