#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Generic LED components."""

from __future__ import print_function
import logging

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component
from cros.factory.utils.type_utils import Enum


class LED(component.DUTComponent):

  Color = Enum(['AUTO', 'OFF', 'RED', 'GREEN', 'BLUE', 'YELLOW', 'WHITE',
                'AMBER'])
  """Charger LED colors.

  - ``AUTO``: Use the default logic to select the LED color.
  - ``OFF``: Turn the LED off.
  - others: The respective colors.
  """

  Index = Enum(['POWER', 'BATTERY', 'ADAPTER'])
  """LED names.

  - ``POWER``: Power LED.
  - ``BATTERY``: Battery LED.
  - ``ADAPTER``: Adapter LED.
  """

  def SetColor(self, color, led_name='battery', brightness=None):
    """Sets LED color.

    Args:
      color: LED color of type LED.Color enum.
      led_name: target LED name.
      brightness: LED brightness in percentage [0, 100].
          If color is 'auto' or 'off', brightness is ignored.
    """
    if color not in self.Color:
      raise ValueError('Invalid color')
    if brightness is not None and not isinstance(brightness, int):
      raise TypeError('Invalid brightness')
    # pylint: disable=C0325
    if brightness is not None and not (0 <= brightness <= 100):
      raise ValueError('brightness out-of-range [0, 100]')
    try:
      if color in [self.Color.AUTO, self.Color.OFF]:
        color_brightness = color.lower()
      elif brightness is not None:
        scaled_brightness = int(round(brightness / 100.0 * 255))
        color_brightness = '%s=%d' % (color.lower(), scaled_brightness)
      else:
        color_brightness = color.lower()
      self._dut.CheckCall(['ectool', 'led', led_name, color_brightness])
    except Exception as e:
      logging.exception('Unable to set LED color: %s', e)
      raise
