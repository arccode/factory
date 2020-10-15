#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest
from unittest import mock

from cros.factory.device.audio import config_manager


class MockProcess:
  """A mock class of the return type of Popen."""
  def __init__(self):
    self.returncode = 0

  def wait(self):
    pass

  def communicate(self, commands):
    if 'card_0' in commands:
      return '''
  0: Speaker
  1: Headphone
  2: Internal Mic
  3: Mic
  4: HDMI1
  5: HDMI2
  6: HDMI3
''', ''
    return '''
  0: Speaker
  1: Headphone
  2: Front Mic
  3: Rear Mic
  4: Mic
  5: HDMI1
  6: HDMI2
''', ''

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
    device.Popen.side_effect = [MockProcess(), MockProcess()]
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

    self.assertEqual(device.Popen.call_count, 2)

    # pylint: disable=protected-access
    self.assertEqual(config_mgr._card_device_map, {
        '0': {
            config_manager.AudioDeviceType.Dmic: "Internal Mic",
            config_manager.AudioDeviceType.Extmic: "Mic",
            config_manager.AudioDeviceType.Headphone: "Headphone",
            config_manager.AudioDeviceType.Speaker: "Speaker",
        },
        '2': {
            config_manager.AudioDeviceType.Dmic: "Front Mic",
            config_manager.AudioDeviceType.Dmic2: "Rear Mic",
            config_manager.AudioDeviceType.Extmic: "Mic",
            config_manager.AudioDeviceType.Headphone: "Headphone",
            config_manager.AudioDeviceType.Speaker: "Speaker",
        },
    })

if __name__ == '__main__':
  unittest.main()
