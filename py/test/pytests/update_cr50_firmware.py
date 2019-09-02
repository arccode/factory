# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Update Cr50 firmware.

Description
-----------
This test provides two functionalities, toggled by the test argument ``method``.

1. In `update mode`, this test calls `gsctool` on DUT to update Cr50 firmware
   in upstart mode (the actuall upgration will happen in the next reboot).
2. In `check mode`, this test calls `gsctool` on DUT to check if the cr50
   firmware version is greater than or equal to the given firmware image.

The Cr50 firmware image to update or compare is either from a given path in
station or DUT, or from the release partition on DUT.

To prepare Cr50 firmware image on station, download the release image with
desired Cr50 firmware image and find the image in DEFAULT_FIRMWARE_PATH below.

Test Procedure
--------------
This is an automatic test that doesn't need any user interaction.

1. Firstly, this test will create a DUT link.
2. If Cr50 firmware image source is from station, the image would be sent to
   DUT.
3. If the Cr50 image is in release partition, the test mounts the release
   partition to get the Cr50 image.
4. If `method` is set to `UPDATE`, DUT runs `gsctool` to update
   Cr50 firmware using the specified Cr50 image.
5. If `method` is set to `CHECK_VERSION`, DUT runs `gsctool` to check
   whether the Cr50 firmware version is greater than or equals to the
   specified Cr50 image.

Dependency
----------
- DUT link must be ready before running this test.
- `gsctool` on DUT.
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

To check if Cr50 firmware version is greater than or equals to the Cr50 image
in the release image::

  {
    "pytest_name": "update_cr50_firmware",
    "args": {
      "method": "CHECK_VERSION"
    }
  }
"""

from distutils import version
import functools
import logging
import os
import re

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.gooftool import common as gooftool_common
from cros.factory.gooftool import gsctool
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils


GSCTOOL = '/usr/sbin/gsctool'
DEFAULT_FIRMWARE_PATH = '/opt/google/cr50/firmware/cr50.bin.prod'
BOARD_ID_FLAG_RE = re.compile(r'^IMAGE_BID_FLAGS=([0-9a-f]*)', re.MULTILINE)
PREPVT_FLAG_MASK = 0x7F


class UpdateCr50FirmwareTest(test_case.TestCase):
  _METHOD_TYPE = type_utils.Enum(['UPDATE', 'CHECK_VERSION'])

  ARGS = [
      Arg('firmware_file', str, 'The full path of the firmware.',
          default=None),
      Arg('from_release', bool, 'Find the firmware from release rootfs.',
          default=True),
      Arg('skip_prepvt_flag_check',
          bool, 'Skip prepvt flag check. For non-dogfood devcies, '
          'we should always use prod firmware, rather than prepvt one. '
          'A dogfood device can use prod firmware, as long as the board id'
          'setting is correct. The dogfood device will update to the prepvt '
          'firmware when first time boot to recovery image. '
          'http://crbug.com/802235',
          default=False),
      Arg('method', _METHOD_TYPE,
          'Specify whether to update the Cr50 firmware or to check the '
          'firmware version.',
          default=_METHOD_TYPE.UPDATE),
      Arg('check_version_retry_timeout', int,
          'If the version is not matched, retry the check after the specific '
          'seconds.  Set to `0` to disable the retry.',
          default=10)
  ]

  ui_class = test_ui.ScrollableLogUI

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

    dut_shell = functools.partial(gooftool_common.Shell, sys_interface=self.dut)
    self.gsctool = gsctool.GSCTool(shell=dut_shell)

  def runTest(self):
    """Update Cr50 firmware."""
    if self.args.firmware_file is None:
      self.assertEqual(
          self.args.from_release, True,
          'Must set "from_release" to True if not specifiying firmware_file')
      self.args.firmware_file = DEFAULT_FIRMWARE_PATH

    self.assertEqual(self.args.firmware_file[0], '/',
                     'firmware_file should be a full path')

    self._LogCr50Info()

    if self.args.method == self._METHOD_TYPE.UPDATE:
      method_func = self._UpdateCr50Firmware
    else:
      method_func = self._CheckCr50FirmwareVersion

    if self.args.from_release:
      with sys_utils.MountPartition(
          self.dut.partitions.RELEASE_ROOTFS.path, dut=self.dut) as root:
        method_func(os.path.join(root, self.args.firmware_file[1:]))
    else:
      if self.dut.link.IsLocal():
        method_func(self.args.firmware_file)
      else:
        with self.dut.temp.TempFile() as dut_temp_file:
          self.dut.SendFile(self.args.firmware_file, dut_temp_file)
          method_func(dut_temp_file)

  def _LogCr50Info(self):
    # TODO(yhong): Centralize the logic to invoking gsctool commands to
    #     `cros.factory.gooftool.gsctool`.
    # Report running Cr50 firmware versions
    self.ui.PipeProcessOutputToUI([gsctool.GSCTOOL_PATH, '-a', '-f'])
    # Get Info1 board ID fields
    self.ui.PipeProcessOutputToUI([gsctool.GSCTOOL_PATH, '-a', '-i'])

  def _IsPrePVTFirmware(self, firmware_file):
    image_info = self.gsctool.GetImageInfo(firmware_file)
    logging.info('Cr50 firmware board ID flags: %s',
                 hex(image_info.board_id_flags))
    testlog.UpdateParam('board_id_flags',
                        description='Board ID of the firmware image.')
    testlog.LogParam('board_id_flags', image_info.board_id_flags)
    return image_info.board_id_flags & PREPVT_FLAG_MASK

  def _UpdateCr50Firmware(self, firmware_file):
    if not self.args.skip_prepvt_flag_check:
      if self._IsPrePVTFirmware(firmware_file):
        raise ValueError('Cr50 firmware board ID flag is PrePVT.')

    image_info = self.gsctool.GetImageInfo(firmware_file)
    fw_ver = self.gsctool.GetCr50FirmwareVersion()

    msg = 'Update the Cr50 firmware from version %r to %r.' % (fw_ver,
                                                               image_info)
    self.ui.SetState(msg)
    session.console.info(msg)
    update_result = self.gsctool.UpdateCr50Firmware(firmware_file)
    session.console.info('Cr50 firmware update complete: %s.', update_result)

  def _CheckCr50FirmwareVersion(self, firmware_file):
    testlog.UpdateParam('expected_ro_fw_version',
                        description='The expected RO FW version.')
    testlog.UpdateParam('expected_rw_fw_version',
                        description='The expected RW FW version.')
    testlog.UpdateParam('ro_fw_version', description='The RO FW version.')
    testlog.UpdateParam('rw_fw_version', description='The RW FW version.')

    image_info = self.gsctool.GetImageInfo(firmware_file)
    testlog.LogParam('expected_ro_fw_version', image_info.ro_fw_version)
    testlog.LogParam('expected_rw_fw_version', image_info.rw_fw_version)

    def _Check():
      self.ui.SetState('Get the current Cr50 firmware version.')
      fw_ver = self.gsctool.GetCr50FirmwareVersion()
      testlog.LogParam('ro_fw_version', fw_ver.ro_version)
      testlog.LogParam('rw_fw_version', fw_ver.rw_version)
      for name in ('ro', 'rw'):
        actual = getattr(fw_ver, name + '_version')
        expect = getattr(image_info, name + '_fw_version')
        if version.StrictVersion(actual) < version.StrictVersion(expect):
          raise type_utils.TestFailure(
              '%s FW version is old (actual=%r, expect=%r)' %
              (name.upper(), actual, expect))

    try:
      _Check()
    except type_utils.TestFailure:
      if self.args.check_version_retry_timeout <= 0:
        raise
      self.ui.SetState('Version is old, sleep for %d seconds and re-check.' %
                       self.args.check_version_retry_timeout)
      self.Sleep(self.args.check_version_retry_timeout)
      _Check()
