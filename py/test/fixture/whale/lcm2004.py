# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides interfaces to initialize and control LCM2004."""

from cros.factory.test.fixture import bft_fixture as bft

# shortcut
BFT = bft.BFTFixture


class Lcm2004:
  """Controls LCM2004 in Whale fixture."""

  _LCM_ROW = {
      BFT.LcmRow.ROW0: 'r0',
      BFT.LcmRow.ROW1: 'r1',
      BFT.LcmRow.ROW2: 'r2',
      BFT.LcmRow.ROW3: 'r3',
  }

  _LCM_COMMAND = {
      BFT.LcmCommand.BACKLIGHT_OFF: 'bkloff',
      BFT.LcmCommand.BACKLIGHT_ON: 'bklon',
      BFT.LcmCommand.CLEAR: 'clear',
      BFT.LcmCommand.HOME: 'home',
  }

  def __init__(self, servo):
    """Constructor.

    Args:
      servo: ServoClient object.
    """
    self._servo = servo

  def SetLcmText(self, row, message):
    """Shows a message to a given row of LCM.

    Args:
      row: row number defined in _LcmRow.
      message: a message to show on LCM.
    """
    row_number = Lcm2004._LCM_ROW[row]

    self._servo.whale_lcm_row = row_number
    self._servo.whale_lcm_text = message

  def IssueLcmCommand(self, action):
    """Issues a command to LCM.

    Args:
      action: action defined in _LCM_COMMAND.
    """
    action_name = Lcm2004._LCM_COMMAND[action]

    self._servo.whale_lcm_cmd = action_name
