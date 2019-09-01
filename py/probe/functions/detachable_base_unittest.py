#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import detachable_base


def FakeCheckOutput(cmd, *unused_args, **unused_kwargs):
  return cmd

class DetachableBaseFunctionTest(unittest.TestCase):
  @mock.patch('cros.factory.utils.process_utils.CheckOutput',
              side_effect=FakeCheckOutput)
  def testNormal(self, unused_mock_check_output):
    result = detachable_base.DetachableBaseFunction()()
    self.assertEquals(
        result,
        [{'ro_version': 'hammer_info.py ro_version',
          'rw_version': 'hammer_info.py rw_version',
          'wp_screw': 'hammer_info.py wp_screw',
          'wp_all': 'hammer_info.py wp_all',
          'touchpad_id': 'hammer_info.py touchpad_id',
          'touchpad_pid': 'hammer_info.py touchpad_pid',
          'touchpad_fw_version': 'hammer_info.py touchpad_fw_version',
          'touchpad_fw_checksum': 'hammer_info.py touchpad_fw_checksum',
          'key_version': 'hammer_info.py key_version',
          'challenge_status': 'hammer_info.py challenge_status'}])


if __name__ == '__main__':
  unittest.main()
