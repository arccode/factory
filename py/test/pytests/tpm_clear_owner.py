# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Requests that the firmware clear the TPM owner on the next reboot.

This should generally be followed by a reboot step.
"""

import unittest

from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils


class ClearTPMOwnerRequest(unittest.TestCase):
  ARGS = [
      Arg('only_check_clear_done', bool, 'Only check crossystem '
          'clear_tpm_owner_done=1', default=False)]

  def runTest(self):
    if self.args.only_check_clear_done:
      self.assertEqual(
          process_utils.CheckOutput(['crossystem', 'clear_tpm_owner_done']),
          '1')
    else:
      process_utils.Spawn(['crossystem', 'clear_tpm_owner_request=1'],
                          check_call=True)
