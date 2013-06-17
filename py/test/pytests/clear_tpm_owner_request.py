# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''
Requests that the firmware clear the TPM owner on the next reboot.

This should generally be followed by a reboot step.
'''

import unittest

import factory_common # pylint: disable=W0611
from cros.factory.test.args import Arg
from cros.factory.utils.process_utils import Spawn, CheckOutput


class ClearTPMOwnerRequest(unittest.TestCase):
  ARGS = [
    Arg('only_check_clear_done', bool, 'Only check crossystem '
        'clear_tpm_owner_done=1', default=False)]
  def runTest(self):
    if self.args.only_check_clear_done:
      self.assertEquals(CheckOutput(['crossystem', 'clear_tpm_owner_done']),
                        '1')
    else:
      Spawn(['crossystem', 'clear_tpm_owner_request=1'],
            check_call=True)
