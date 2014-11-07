# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provide interfaces to initialize and read Whale color sensor."""

import ast
import logging

import factory_common  # pylint: disable=W0611
import cros.factory.test.fixture.bft_fixture as bft

# shortcut
BFT = bft.BFTFixture

class ColorSensor(object):
  """Whale color sensor."""

  # mapping from color names in bft.conf to BFTFixture.LEDColor
  _COLOR_NAMES = {
    'red': BFT.LEDColor.RED,
    'green': BFT.LEDColor.GREEN,
    'yellow': BFT.LEDColor.YELLOW
  }

  # config names
  _CONFIG_TIMING = 'color_sensor_timing'
  _CONFIG_GAIN = 'color_sensor_gain'
  _CONFIG_COLOR = 'color_sensor_color'
  _REQUIRED_PARAMS = (_CONFIG_TIMING, _CONFIG_GAIN, _CONFIG_COLOR)

  def __init__(self, servo, sensor_index, params):
    """Constructor.

    Args:
      servo: ServoClient object.
      sensor_index: Index of color sensor (starting from 1).
      params: Parameters loaded from bft.conf.
    """
    # Verify parameters first because it's easy to make mistakes.
    for config in self._REQUIRED_PARAMS:
      if config not in params:
        raise ValueError('Missing parameter %s' % config)
      if sensor_index not in params[config]:
        raise ValueError('Parameter %s does not contain sensor index %d' %
                         (config, sensor_index))
    for color_name in params[self._CONFIG_COLOR][sensor_index]:
      if color_name not in self._COLOR_NAMES:
        raise ValueError('Unsupport color name %s in parameters' % color_name)

    # Initialize the color sensor hardware.
    if sensor_index == 1:
      servo.whale_color1_timing = (
          params[self._CONFIG_TIMING][sensor_index])
      servo.whale_color1_gain = params[self._CONFIG_GAIN][sensor_index]
    else:
      raise ValueError('Sensor index %s is unsupported' % sensor_index)

    self._servo = servo
    self._sensor_index = sensor_index
    self._color_params = params[self._CONFIG_COLOR][sensor_index]

  @classmethod
  def HasRequiredParams(cls, params):
    """Checks if params has required parameters.

    Args:
      params: a dict contains parameters

    Returns:
      True if params contains all required parameters.
    """
    return all(p in params for p in cls._REQUIRED_PARAMS)

  @staticmethod
  def _CompareHue(hue1, hue2, tolerance):
    """Compares hue values.

    Because hue value is cyclic from 0.0 to 1.0. It treats values close to 0.0
    in similar way to values close to 1.0.

    Args:
      hue1: First hue value.
      hue2: Second hue value.
      tolerance: Allowed difference between hue[12].

    Returns:
      Whether hue1 and hue2 are close enough.
    """
    return (abs(hue1 - hue2) <= tolerance or
            abs(hue1 - hue2 - 1.0) <= tolerance or
            abs(hue1 - hue2 + 1.0) <= tolerance)

  def ReadColor(self):
    """Reads color value from sensor.

    Returns:
      BFTFixture.LEDColor; BFTFixture.LEDColor.OFF if no color is detected.
    """
    if self._sensor_index == 1:
      # Servo returns a string containing list expression.
      read_h, read_s, read_v = ast.literal_eval(self._servo.whale_color1_HSV)
    else:
      raise ValueError('Sensor index %s is unsupported' % self._sensor_index)
    logging.info('Read Hue=%.3f, Saturation=%.3f, Lightness=%.3f',
                 read_h, read_s, read_v)

    for color_name in self._color_params:
      thresholds =  self._color_params[color_name]
      color_hue = thresholds['hue']
      hue_tolerance = thresholds['hue_tolerance']
      min_saturation = thresholds['min_saturation']
      min_lightness = thresholds['min_lightness']
      if (self._CompareHue(read_h, color_hue, hue_tolerance) and
          read_s >= min_saturation and read_v >= min_lightness):
        logging.info('Match color %s with HSV criteria '
                     '(%.3f +/- %.3f, >= %.3f, >= %.3f)', color_name,
                     color_hue, hue_tolerance, min_saturation, min_lightness)
        return self._COLOR_NAMES[color_name]

    logging.info('Do not match any color')
    return BFT.LEDColor.OFF
