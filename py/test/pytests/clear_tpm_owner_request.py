# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''
Requests that the firmware clear the TPM owner on the next reboot.

This should generally be followed by a reboot step.
'''

import factory_common # pylint: disable=W0611
import unittest

from cros.factory.utils.process_utils import Spawn


class ClearTPMOwnerRequest(unittest.TestCase):
  ARGS = []
  def runTest(self):
    Spawn(['crossystem', 'clear_tpm_owner_request=1'],
          check_call=True)
