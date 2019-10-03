# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Applies new kernel to DUT (for testing).

Description
-----------
This test helps replacing kernel on DUT.

Sometimes in early builds, we do need to update kernel on DUT for enabling extra
drivers, bug fixes, or few workarounds.  Sometimes we may want to enable or
disable few kernel command line arguments.

Another case is to allow finalizing with a DEV signed firmware (due to last
minute changes in manufacturing line and no time to wait for a signed complete
release), we have to re-sign release image kernel with DEV keys (see
http://go/cros-factory-fw-in-early-builds for more details).

All these leads to the demand of updating kernel on DUT, with the ability to
resign or changing kernel command line, and that's all supported by this test.


Test Procedure
--------------
This is an automated test without user interaction.

After started, the test will replace kernel on device partition by given
arguments.

Dependency
----------
- The DUT must be running Chrome OS image.
- ``flashrom`` and ``gooftool`` are needed if argument ``to_release`` is True.
- ``futility`` is needed if argument ``kernel_config`` is set.

Examples
--------
To replace the kernel on TEST image partition and keep old kernel command line::

  {
    "pytest_name": "update_kernel",
    "args": {
      "kernel_image": "/usr/local/factory/board/test_kernel.bin"
    }
  }

To re-sign kernel on RELEASE image partition with DEV key::

  {
    "pytest_name": "update_kernel",
    "args": {
      "to_release": true
    }
  }

To change kernel command line of the kernel on TEST image partition::

  {
    "pytest_name": "update_kernel",
    "args": {
      "kernel_config": "/usr/local/factory/board/test_kernel.cmdline"
    }
  }

"""

import os
import unittest

from cros.factory.device import device_utils
from cros.factory.probe.functions import chromeos_firmware
from cros.factory.test.utils import deploy_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


_DEVKEY = 'b11d74edd286c144e1135b49e7f0bc20cf041f10'


class UpdateKernel(unittest.TestCase):
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
      # pylint: disable=dict-values-not-iterating
      probed_keys = chromeos_firmware.ChromeosFirmwareFunction.ProbeDevices(
          chromeos_firmware.FIELDS.firmware_keys).values()
      fw_keys = [key.split('#')[1] for key in probed_keys]
      self.assertIn(_DEVKEY, fw_keys)

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
