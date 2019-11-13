# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to initiate and verify recovery mode memory re-train process.

Description
-----------
The test either request memory re-training on next boot (if ``mode`` is
``'create'``), or verify the mrc cache trained (if ``mode`` is ``'verify'``).

Test Procedure
--------------
This is an automated test without user interaction.

Dependency
----------
``flashrom``, ``crossystem`` and ``futility validate_rec_mrc``.

Examples
--------
To generate mrc cache on next boot, reboot, and verify the generated mrc cache,
add this in test list::

  {
    "label": "i18n! MRC Cache",
    "subtests": [
      {
        "pytest_name": "mrc_cache",
        "label": "i18n! Create Cache",
        "args": {
          "mode": "create"
        }
      },
      "RebootStep",
      {
        "pytest_name": "mrc_cache",
        "label": "i18n! Verify Cache",
        "args": {
          "mode": "verify"
        }
      }
    ]
  }
"""

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils.file_utils import UnopenedTemporaryFile

ARCH_TO_FMAP = {
    'x86': 'RECOVERY_MRC_CACHE',
    'arm': 'RW_DDR_TRAINING',
}

class MrcCacheTest(unittest.TestCase):
  ARGS = [
      Arg('mode', str,
          'Specify the phase of the test, valid values are:\n'
          '- "create": request memory retraining on next boot.\n'
          '- "verify": verify the mrc cache created by previous step.\n'),
      Arg('fmap_name', str,
          'Specify the FMAP section name used for memory training. '
          'Essentially this is passed to flashrom as part of "-i" option. '
          'e.g. "RECOVERY_MRC_CACHE" for x86 and "RW_DDR_TRAINING" for ARM.',
          default=None)
      ]

  def Create(self):
    # check section existence
    self.dut.CheckCall('flashrom -p host -r /dev/null -i %s' %
                       self.args.fmap_name)
    # erase old section
    self.dut.CheckCall('flashrom -p host -E -i %s' % self.args.fmap_name)
    # request to re-train memory
    self.dut.CheckCall('crossystem recovery_request=0xC4')

  def Verify(self):
    with UnopenedTemporaryFile() as f:
      self.dut.CheckCall('flashrom -p host -r /dev/null -i %s:%s' %
                         (self.args.fmap_name, f))
      self.dut.CheckCall('futility validate_rec_mrc %s' % f)

  def CheckArch(self):
    return self.dut.CheckOutput('crossystem arch')

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def runTest(self):
    if self.args.fmap_name is None:
      arch = self.CheckArch()
      if arch in ARCH_TO_FMAP:
        self.args.fmap_name = ARCH_TO_FMAP[arch]
      else:
        self.fail('Need to specify FMAP name for unknown platform %s' % arch)

    if self.args.mode == 'create':
      self.Create()
    elif self.args.mode == 'verify':
      self.Verify()
    else:
      self.fail('Unknown mode: %s' % self.args.mode)
