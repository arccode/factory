# -*- coding: utf-8 -*-
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is a factory test to check the LED brightness."""

import factory_common  # pylint: disable=W0611
from cros.factory.device import led as led_module
from cros.factory.test.pytests.brightness import brightness
from cros.factory.utils.arg_utils import Arg, MergeArgs


LEDColor = led_module.LED.Color


class LEDBrightnessTest(brightness.BrightnessTest):
  ARGS = MergeArgs(brightness.BrightnessTest.ARGS, [
      Arg('led_name', str, 'The name of the LED to test.', default='battery'),
      Arg('color', str, 'The color to test.', default=LEDColor.WHITE)])

  def tearDown(self):
    self.dut.led.SetColor(LEDColor.AUTO, led_name=self.args.led_name)

  def _SetBrightnessLevel(self, level):
    self.dut.led.SetColor(self.args.color,
                          led_name=self.args.led_name,
                          brightness=level)
