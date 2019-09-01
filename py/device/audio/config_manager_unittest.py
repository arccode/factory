#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.device.audio import config_manager


class UCMConfigManagerTest(unittest.TestCase):
  @mock.patch('os.path.isdir')
  def testGetCardNameMapFromAplay(self, mock_isdir):
    device = mock.MagicMock()
    mixer_controller = mock.MagicMock()

    device.CallOutput = mock.MagicMock(return_value='''
card 0: card_0 [card_0], device 0: Audio (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 0: card_0 [card_0], device 2: Audio (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: card_1 [card_1], device 3: Audio (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 2: card_2 [card_2], device 8: Audio (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
''')
    device.path = os.path
    mock_isdir.side_effect = lambda path: (
        os.path.basename(path) in ['card_0', 'card_2'])

    config_mgr = config_manager.UCMConfigManager(device, mixer_controller)

    device.CallOutput.assert_any_call(['aplay', '-l'])
    self.assertEqual(device.CallOutput.call_count, 5)

    # pylint: disable=protected-access
    self.assertEqual(config_mgr._card_map, {
        '0': 'card_0',
        '2': 'card_2',
    })


if __name__ == '__main__':
  unittest.main()
