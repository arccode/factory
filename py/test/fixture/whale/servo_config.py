# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Dummy file for board-dependent whale servo configs.

Servo config file for specific board should be placed under board overlays and
named as <board>_servo_config.py, ex. py/test/fixture/whale/ryu_servo_config.py
for ryu board.
"""

import glob
import os

try:
  from cros.factory.utils import type_utils
except ImportError:
  # BB might still using the old toolkit, try to be backward compatible.
  # pylint: disable=no-name-in-module
  from cros.factory import common as type_utils


SERVO_CONFIG_FILENAME_SPEC = '*_servo_config.py'
IMPORT_PATH = 'cros.factory.test.fixture.whale.%s'

# Whale's krill INA dict
WHALE_INA = {
    'krill_vc_connector_ina%d' % i: 'krill_vc_connector_ina%d' % i
    for i in range(1, 17)
}

# Whale's krill ADC list
WHALE_ADC = [
    ('whale_adc%d' % i, 1) for i in range(7)
]

# Whale's feedback dict
FIXTURE_FEEDBACK = type_utils.AttrDict(
    {'FB%d' % i: 'fixture_fb%d' % i for i in range(1, 15)})

def _GetBoardServoConfig():
  """Gets board-dependent servo config file name.

  Returns:
    File name without file extension, ex. samus_servo_config. Return None if no
    matched file is found.
  """
  configs = glob.glob(os.path.join(
      os.path.dirname(os.path.realpath(__file__)), SERVO_CONFIG_FILENAME_SPEC))
  if not configs:
    return None
  return os.path.splitext(os.path.basename(configs[0]))[0]

board_config = _GetBoardServoConfig()
if board_config:
  # Import board-dependent servo config module and update parameters.
  import_config = __import__(IMPORT_PATH % board_config,
                             fromlist=['ServoConfig'])
  WHALE_INA = import_config.WHALE_INA
  WHALE_ADC = import_config.WHALE_ADC
  FIXTURE_FEEDBACK = import_config.FIXTURE_FEEDBACK
