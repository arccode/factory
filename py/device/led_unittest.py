#!/usr/bin/env python3
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for LED."""

import unittest
from unittest import mock

from cros.factory.device import device_types
from cros.factory.device import led as led_module


class LEDTest(unittest.TestCase):
  """Unittest for LED."""

  def setUp(self):
    self.board = mock.Mock(device_types.DeviceBoard)
    self.ectool_led_msg = ('Brightness range for LED 0:\n'
                           '\tred\t: 0x64\n'
                           '\tgreen\t: 0xff\n'
                           '\tblue\t: 0x0\n'
                           '\tyellow\t: 0x1\n'
                           '\twhite\t: 0x0\n'
                           '\tamber\t: 0x0\n')

  def callOutputSideEffect(self, command):
    """It only returns info for BATTERY LED"""
    if command[2] == led_module.LED.CrOSIndexes.BATTERY.lower(
    ) and command[3] == 'query':
      return self.ectool_led_msg
    return None

  def testSetColor(self):
    self.board.CallOutput.side_effect = self.callOutputSideEffect
    led = led_module.LED(self.board)

    led.SetColor(led.Color.RED, brightness=None)
    self.board.CheckCall.assert_called_with(
        ['ectool', 'led', 'battery', 'red=100'])

    led.SetColor(led.Color.YELLOW, brightness=None)
    self.board.CheckCall.assert_called_with(
        ['ectool', 'led', 'battery', 'yellow=1'])

    led.SetColor(led.Color.GREEN, brightness=None)
    self.board.CheckCall.assert_called_with(
        ['ectool', 'led', 'battery', 'green=255'])

    led.SetColor(led.Color.GREEN, brightness=100)
    self.board.CheckCall.assert_called_with(
        ['ectool', 'led', 'battery', 'green=255'])

    led.SetColor(led.Color.GREEN, brightness=50)
    self.board.CheckCall.assert_called_with(
        ['ectool', 'led', 'battery', 'green=128'])

    led.SetColor(led.Color.GREEN, brightness=0)
    self.board.CheckCall.assert_called_with(
        ['ectool', 'led', 'battery', 'green=0'])

    led.SetColor(led.Color.AUTO)
    self.board.CheckCall.assert_called_with(
        ['ectool', 'led', 'battery', 'auto'])

    led.SetColor(led.Color.AUTO, brightness=0)
    self.board.CheckCall.assert_called_with(
        ['ectool', 'led', 'battery', 'auto'])

    led.SetColor(led.Color.OFF)
    self.board.CheckCall.assert_called_with(['ectool', 'led', 'battery', 'off'])

    led.SetColor(led.Color.OFF, brightness=100)
    self.board.CheckCall.assert_called_with(['ectool', 'led', 'battery', 'off'])

  def testMultipleLEDs(self):
    self.board.CallOutput.return_value = self.ectool_led_msg

    led = led_module.LeftRightLED(self.board)
    self.board.CallOutput.assert_any_call(['ectool', 'led', 'left', 'query'])
    self.board.CallOutput.assert_any_call(['ectool', 'led', 'right', 'query'])

    led.SetColor(led.Color.AUTO)
    self.board.CheckCall.assert_any_call(['ectool', 'led', 'left', 'auto'])
    self.board.CheckCall.assert_any_call(['ectool', 'led', 'right', 'auto'])

    led.SetColor(led.Color.GREEN, led_name=led_module.LED.CrOSIndexes.LEFT)
    self.board.CheckCall.assert_called_with(
        ['ectool', 'led', 'left', 'green=255'])

  def testSetColorInvalidInput(self):
    self.board.CallOutput.return_value = ''

    led = led_module.LED(self.board)
    with self.assertRaisesRegex(ValueError, 'Invalid color'):
      led.SetColor('invalid color')
    with self.assertRaisesRegex(TypeError, 'Invalid brightness'):
      led.SetColor(led.Color.RED, brightness='1')
    with self.assertRaisesRegex(ValueError,
                                r'brightness \(255\) out-of-range'):
      led.SetColor(led.Color.RED, brightness=255)

  def testSetColorUnsupportedBoard(self):
    self.board.CallOutput.side_effect = self.callOutputSideEffect
    msg = 'EC returned error 99'
    self.board.CheckCall.side_effect = led_module.LED.Error(msg)

    led = led_module.LED(self.board)
    with self.assertRaisesRegex(device_types.DeviceException, msg):
      led.SetColor(led.Color.RED, brightness=None)


if __name__ == '__main__':
  unittest.main()
