# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Generic LED components."""

from __future__ import print_function

import logging
import re

import factory_common  # pylint: disable=unused-import
from cros.factory.device import types
from cros.factory.utils.type_utils import Enum

_PATTERN = re.compile(r'\t([a-z]+)\t: (0x[0-9A-Fa-f]+)\n')
"""The pattern of entries of output of 'ectool led <name> query'"""

class LED(types.DeviceComponent):
  """LED control using Chrome OS ectool."""

  Color = Enum(['AUTO', 'OFF', 'RED', 'GREEN', 'BLUE', 'YELLOW', 'WHITE',
                'AMBER'])
  """Charger LED colors.

  - ``AUTO``: Use the default logic to select the LED color.
  - ``OFF``: Turn the LED off.
  - others: The respective colors.
  """

  CrOSIndexes = Enum(['BATTERY', 'POWER', 'ADAPTER', 'LEFT', 'RIGHT',
                      'RECOVERY_HWREINIT', 'SYSRQ DEBUG'])
  """All LED names published by `ectool` today.

  Run `ectool led non-exist x` or look up src/platform/ec/util/ectool.c for
  latest known names.

  Note 'SYSRQ DEBUG' is one single index with space in name, not typo.
  """

  Index = Enum([CrOSIndexes.BATTERY])
  """List of LEDs available on DUT. Usually a subset from CrOSIndexes."""

  def __init__(self, device):
    """Probe all maximum brightnesses in advance."""
    super(LED, self).__init__(device)
    self.max_brightnesses = {}
    for name in self.Index:
      output = self._device.CallOutput(
          ['ectool', 'led', name.lower(), 'query']) or ''
      max_brightness = dict((color.lower(), 255) for color in self.Color)
      max_brightness.update((color, int(brightness, 0))
                            for color, brightness in _PATTERN.findall(output))
      self.max_brightnesses.update({name.lower(): max_brightness})


  def SetColor(self, color, led_name=None, brightness=None):
    """Sets LED color.

    Args:
      color: LED color of type LED.Color enum.
      led_name: target LED name, or None for all.
      brightness: LED brightness in percentage [0, 100].
          If color is 'auto' or 'off', brightness is ignored.
    """
    logging.info('LED.SetColor(color: %r, led_name: %r, brightness: %r)',
                 color, led_name, brightness)

    # Check parameters
    if led_name is not None and led_name.upper() not in self.Index:
      raise ValueError('Invalid led name: %r' % led_name)
    if color not in self.Color:
      raise ValueError('Invalid color: %r' % color)
    if brightness is not None:
      if not isinstance(brightness, int):
        raise TypeError('Invalid brightness: %r' %  brightness)
      # pylint: disable=superfluous-parens
      if not (0 <= brightness <= 100):
        raise ValueError('brightness (%d) out-of-range [0, 100]' % brightness)
    else:
      brightness = 100

    # self.Index using Enum will be a frozenset so the for-loop below may be
    # in arbitrary order.
    for name in [led_name] if led_name else self.Index:
      try:
        if color in [self.Color.AUTO, self.Color.OFF]:
          color_brightness = color.lower()
        else:
          max_brightness = self.max_brightnesses[name.lower()][color.lower()]
          scaled_brightness = int(round(brightness / 100.0 * max_brightness))
          color_brightness = '%s=%d' % (color.lower(), scaled_brightness)
      except Exception:
        logging.exception('Failed deciding LED command for %r (%r,%r)',
                          name, color, brightness)
        raise

      try:
        self._device.CheckCall(
            ['ectool', 'led', name.lower(), color_brightness])
      except Exception:
        logging.exception('Unable to set LED %r to %r', name, color_brightness)
        raise


class BatteryLED(LED):
  """Devices with only Battery LED (usually Tablet or Chromebook)."""
  Index = Enum([LED.CrOSIndexes.BATTERY])


class PowerLED(LED):
  """Devices with only Power LED (usually Chromebox)."""
  Index = Enum([LED.CrOSIndexes.POWER])


class BatteryPowerLED(LED):
  """Devices with Battery and Power LEDs (most recent x86 Chromebooks)."""
  Index = Enum([LED.CrOSIndexes.BATTERY, LED.CrOSIndexes.POWER])


class BatteryPowerAdapterLED(LED):
  """Devices with Battery, Power and Adapter LEDs. (older Chromebooks)."""
  Index = Enum([LED.CrOSIndexes.BATTERY, LED.CrOSIndexes.POWER,
                LED.CrOSIndexes.ADAPTER])


class LeftRightLED(LED):
  """Devices with only Left and Right LEDs (modern Chromebooks with 2 TypeC)."""
  Index = Enum([LED.CrOSIndexes.LEFT, LED.CrOSIndexes.RIGHT])


class LeftRightPowerLED(LED):
  """Devices with Left, Right and Power LEDs.

     Modern convertible Chromebooks with 2 TypeC and power button with LED.
  """
  Index = Enum([LED.CrOSIndexes.LEFT, LED.CrOSIndexes.RIGHT,
                LED.CrOSIndexes.POWER])
