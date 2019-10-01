#!/usr/bin/env python2
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for LED."""

from __future__ import print_function

import unittest

import mox
from six import assertRaisesRegex

import factory_common  # pylint: disable=unused-import
from cros.factory.device import led as led_module
from cros.factory.device import types


class LEDTest(unittest.TestCase):
  """Unittest for LED."""

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(types.DeviceBoard)

  def tearDown(self):
    self.mox.UnsetStubs()

  def testSetColor(self):
    msg = ('Brightness range for LED 0:\n'
           '\tred\t: 0x64\n'
           '\tgreen\t: 0xff\n'
           '\tblue\t: 0x0\n'
           '\tyellow\t: 0x1\n'
           '\twhite\t: 0x0\n'
           '\tamber\t: 0x0\n')
    self.board.CallOutput(['ectool', 'led', 'battery', 'query']).AndReturn(msg)

    self.board.CheckCall(['ectool', 'led', 'battery', 'red=100'])
    self.board.CheckCall(['ectool', 'led', 'battery', 'yellow=1'])
    self.board.CheckCall(['ectool', 'led', 'battery', 'green=255'])

    self.board.CheckCall(['ectool', 'led', 'battery', 'green=255'])
    self.board.CheckCall(['ectool', 'led', 'battery', 'green=128'])
    self.board.CheckCall(['ectool', 'led', 'battery', 'green=0'])

    self.board.CheckCall(['ectool', 'led', 'battery', 'auto'])
    # brightness does not take effect.
    self.board.CheckCall(['ectool', 'led', 'battery', 'auto'])

    # Turn off battery LED.
    self.board.CheckCall(['ectool', 'led', 'battery', 'off'])
    self.board.CheckCall(['ectool', 'led', 'battery', 'off'])

    self.mox.ReplayAll()

    led = led_module.LED(self.board)

    led.SetColor(led.Color.RED, brightness=None)
    led.SetColor(led.Color.YELLOW, brightness=None)
    led.SetColor(led.Color.GREEN, brightness=None)

    led.SetColor(led.Color.GREEN, brightness=100)
    led.SetColor(led.Color.GREEN, brightness=50)
    led.SetColor(led.Color.GREEN, brightness=0)

    led.SetColor(led.Color.AUTO)
    led.SetColor(led.Color.AUTO, brightness=0)

    led.SetColor(led.Color.OFF)
    led.SetColor(led.Color.OFF, brightness=100)
    self.mox.VerifyAll()

  def testMultipleLEDs(self):
    self.board.CallOutput(['ectool', 'led', 'left', 'query']).InAnyOrder()
    self.board.CallOutput(['ectool', 'led', 'right', 'query']).InAnyOrder()
    self.board.CheckCall(['ectool', 'led', 'left', 'auto']).InAnyOrder()
    self.board.CheckCall(['ectool', 'led', 'right', 'auto']).InAnyOrder()
    self.board.CheckCall(['ectool', 'led', 'left', 'green=255'])
    self.mox.ReplayAll()
    led = led_module.LeftRightLED(self.board)
    led.SetColor(led.Color.AUTO)
    led.SetColor(led.Color.GREEN, led_name='left')
    self.mox.VerifyAll()

  def testSetColorInvalidInput(self):
    self.board.CallOutput(['ectool', 'led', 'battery', 'query'])
    self.mox.ReplayAll()
    led = led_module.LED(self.board)
    with assertRaisesRegex(self, ValueError, 'Invalid color'):
      led.SetColor('invalid color')
    with assertRaisesRegex(self, TypeError, 'Invalid brightness'):
      led.SetColor(led.Color.RED, brightness='1')
    with assertRaisesRegex(self, ValueError,
                           r'brightness \(255\) out-of-range'):
      led.SetColor(led.Color.RED, brightness=255)

  def testSetColorUnsupportedBoard(self):
    self.board.CallOutput(['ectool', 'led', 'battery', 'query'])
    msg = 'EC returned error 99'
    self.board.CheckCall(['ectool', 'led', 'battery', 'red=255']).AndRaise(
        led_module.LED.Error(msg))
    self.mox.ReplayAll()
    led = led_module.LED(self.board)
    with assertRaisesRegex(self, types.DeviceException, msg):
      led.SetColor(led.Color.RED, brightness=None)
    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()
