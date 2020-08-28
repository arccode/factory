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

from cros.factory.device import device_utils
from cros.factory.tools import mrc_cache
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils.type_utils import Enum


TestMode = Enum(['create', 'verify'])


class MrcCacheTest(unittest.TestCase):
  ARGS = [
      Arg(
          'mode', TestMode, 'Specify the phase of the test, valid values are:\n'
          '- "create": request memory retraining on next boot.\n'
          '- "verify": verify the mrc cache created by previous step.\n')
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def runTest(self):
    if self.args.mode == TestMode.create:
      mrc_cache.EraseTrainingData(self.dut)
    elif self.args.mode == TestMode.verify:
      mrc_cache.VerifyTrainingData(self.dut)
