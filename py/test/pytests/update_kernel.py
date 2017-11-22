# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Applies new kernel to DUT (for testing)."""

import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import deploy_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


_CSS = 'test-template { text-align: left; }'
_DEVKEY = 'b11d74edd286c144e1135b49e7f0bc20cf041f10'


class UpdateFirmwareTest(unittest.TestCase):
  ARGS = [
      # TODO(hungte) Support compressed image, or download from factory server.
      Arg('kernel_image', str, 'Full path of kernel.bin',
          default=None),
      Arg('kernel_config', str,
          'Path to a file containing kernel command line.',
          default=None),
      Arg('to_release', bool,
          'Set to True to update on release partition, '
          'otherwise update on test partition.',
          default=False)
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    if self.args.kernel_image is not None:
      self.assertTrue(os.path.isfile(self.args.kernel_image),
                      msg='%s is missing.' % self.args.kernel_image)
    if self.args.kernel_config is not None:
      self.assertTrue(os.path.isfile(self.args.kernel_config),
                      msg='%s is missing.' % self.args.kernel_config)

    self._ui = test_ui.UI(css=_CSS)
    self._template = ui_templates.OneScrollableSection(self._ui)

  def UpdateKernel(self):
    """Apply new kernel.

    Gets current kernel config, re-sign by make_dev_ssd, then write into system.
    """
    if self.args.to_release:
      # verify release partition is in dev channel
      factory_tool = deploy_utils.CreateFactoryTools(self._dut)
      factory_tool.CheckCall(['gooftool', 'verify_release_channel',
                              '--enforced_release_channels', 'dev'])
      # verify firmware is dev key
      with self._dut.temp.TempFile() as temp_file:
        self._dut.CheckCall(['flashrom', '-r', temp_file, '-i', 'GBB', '-i',
                             'FMAP'])
        key_info = factory_tool.CheckOutput(['gooftool', 'get_firmware_hash',
                                             '--file', temp_file])
        self.assertIn(_DEVKEY, key_info)

    if self.args.to_release:
      kerndev = self._dut.partitions.RELEASE_KERNEL
    else:
      kerndev = self._dut.partitions.FACTORY_KERNEL
    kernel_id = str(kerndev.index)

    if self.args.kernel_config is None:
      kernel_config = process_utils.CheckOutput(
          ["futility", "dump_kernel_config", kerndev.path])
    else:
      kernel_config = file_utils.ReadFile(self.args.kernel_config)

    if self.args.kernel_image is not None:
      # Directly write into kernel partition.
      with open(self.args.kernel_image, 'r') as f:
        self._dut.WriteSpecialFile(kerndev.path, f.read())

    config_suffix = ".%s" % kernel_id
    with self._dut.temp.TempFile(suffix=config_suffix) as config_file:
      self._dut.WriteFile(config_file, kernel_config)
      process_utils.LogAndCheckCall([
          "/usr/share/vboot/bin/make_dev_ssd.sh", "--partitions", kernel_id,
          "--set_config", config_file[:-len(config_suffix)]])

  def runTest(self):
    self.UpdateKernel()
