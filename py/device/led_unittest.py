#!/usr/bin/env python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for LED."""

from __future__ import print_function

import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.device import led
from cros.factory.device import types


class LEDTest(unittest.TestCase):
  """Unittest for LED."""

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(types.DeviceBoard)
    self.led = led.LED(self.board)

  def tearDown(self):
    self.mox.UnsetStubs()

  def testSetColor(self):
    self.board.CheckCall(['ectool', 'led', 'battery', 'red'])
    self.board.CheckCall(['ectool', 'led', 'battery', 'yellow'])
    self.board.CheckCall(['ectool', 'led', 'battery', 'green'])

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
    self.led.SetColor(self.led.Color.RED, brightness=None)
    self.led.SetColor(self.led.Color.YELLOW, brightness=None)
    self.led.SetColor(self.led.Color.GREEN, brightness=None)

    self.led.SetColor(self.led.Color.GREEN, brightness=100)
    self.led.SetColor(self.led.Color.GREEN, brightness=50)
    self.led.SetColor(self.led.Color.GREEN, brightness=0)

    self.led.SetColor(self.led.Color.AUTO)
    self.led.SetColor(self.led.Color.AUTO, brightness=0)

    self.led.SetColor(self.led.Color.OFF)
    self.led.SetColor(self.led.Color.OFF, brightness=100)
    self.mox.VerifyAll()

  def testMultipleLEDs(self):
    self.led = led.LeftRightLED(self.board)
    self.board.CheckCall(['ectool', 'led', 'left', 'auto']).InAnyOrder()
    self.board.CheckCall(['ectool', 'led', 'right', 'auto']).InAnyOrder()
    self.board.CheckCall(['ectool', 'led', 'left', 'green'])
    self.mox.ReplayAll()
    self.led.SetColor(self.led.Color.AUTO)
    self.led.SetColor(self.led.Color.GREEN, led_name='left')
    self.mox.VerifyAll()

  def testSetColorInvalidInput(self):
    with self.assertRaisesRegexp(ValueError, 'Invalid color'):
      self.led.SetColor('invalid color')
    with self.assertRaisesRegexp(TypeError, 'Invalid brightness'):
      self.led.SetColor(self.led.Color.RED, brightness='1')
    with self.assertRaisesRegexp(ValueError,
                                 r'brightness \(255\) out-of-range'):
      self.led.SetColor(self.led.Color.RED, brightness=255)

  def testSetColorUnsupportedBoard(self):
    msg = 'EC returned error 99'
    self.board.CheckCall(['ectool', 'led', 'battery', 'red']).AndRaise(
        self.led.Error(msg))
    self.mox.ReplayAll()
    with self.assertRaisesRegexp(types.DeviceException, msg):
      self.led.SetColor(self.led.Color.RED, brightness=None)
    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()
