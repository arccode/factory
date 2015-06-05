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

import factory_common  # pylint: disable=W0611

SERVO_CONFIG_FILENAME_SPEC = '*_servo_config.py'
IMPORT_PATH = 'cros.factory.test.fixture.whale.%s'

WHALE_INA = dict()  # Whale's krill INA dict
FIXTURE_FEEDBACK = dict()  # Whale's fixture feedback dict

def _GetBoardServoConfig():
  """Gets board-dependent servo config file name.

  Returns:
    File name without file extension, ex. samus_servo_config. Return None if no
    matched file is found.
  """
  configs = glob.glob(os.path.join(
      os.path.dirname(os.path.realpath(__file__)), SERVO_CONFIG_FILENAME_SPEC))
  if len(configs) == 0:
    return None
  return os.path.splitext(os.path.basename(configs[0]))[0]

board_config = _GetBoardServoConfig()
if board_config:
  # Import board-dependent servo config module and update parameters.
  import_config = __import__(IMPORT_PATH % board_config,
                             fromlist=['ServoConfig'])
  WHALE_INA = import_config.WHALE_INA
  FIXTURE_FEEDBACK = import_config.FIXTURE_FEEDBACK
