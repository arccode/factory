# -*- mode: python; coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Step to control Arduino digital pins.

This is not actually a test, it's just a simple step that controls Arduino's
digital pins accroding to its argument.

This step is intended to be used with
"py/test/fixture/arduino_digital_pin_controller.ino", so before using this
step, upload the .ino program to the Arduino board first. Note that the .ino
program resets all pins to LOW initially, so we only have to specify pins that
should be high here.

The following example sets pin 3 and 5 to HIGH:
  FactoryTest(
      id='SwitchAntenna',
      label_zh=u'切换天线',
      pytest_name='arduino_digital_pins',
      dargs=dict(high_pins=[3, 5]]))
"""


import logging
import unittest

import factory_common  # pylint: disable=W0611

from cros.factory.test.args import Arg
from cros.factory.test.fixture import arduino


class ArduinoDigitalPinsStep(unittest.TestCase):
  ARGS = [
      Arg('high_pins', list, 'List of pins that will be set to HIGH, '
          'e.g., [3, 5] will set both pin 3 and 5 to HIGH',
          optional=False),
  ]

  def setUp(self):
    controller = arduino.ArduinoDigitalPinController()
    controller.Connect()
    for pin in self.args.high_pins:
      logging.info('Change pin %d to HIGH', pin)
      controller.SetPin(pin, True)
    controller.Disconnect()

  def runTest(self):
    pass
