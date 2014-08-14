# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Emulates keyboard scan."""

import time

import factory_common  # pylint: disable=W0611
from cros.factory.test.fixture.whale import servo_client


class KeyboardEmulator(object):
  """Controls keyboard emulator in Whale fixture.

  Keyboard emulator provides two methods: one is to trigger all row-column
  crossings in sequence; the other is to emulate pressing of single or
  multiple key(s) for a specified period.
  """
  # Shortcuts to Whale's control.
  # pylint: disable=E1101
  _CONTROL = servo_client.WHALE_CONTROL

  def __init__(self, servo):
    """Constructor.

    Args:
      servo: Instance of servo_client.ServoClient
    """
    self._servo = servo
    self._Reset()
    self._LatchOutput()

  def _LatchOutput(self):
    """Outputs 16 GPIOs from the 2 shift registers."""
    self._servo.Click(self._CONTROL.KEYBOARD_SHIFT_REGISTER_LATCH)

  def _Reset(self):
    """Resets the 2 shift registers."""
    self._servo.Click(self._CONTROL.KEYBOARD_SHIFT_REGISTER_RESET)

  def _Emulate(self, word, latch_shift):
    """Emulates row-column crossing.

    For example, if the word is 0b1000000000000000, the variation in
    two shift registers will be:
    Shift 1: 0b0000000000000001
    Shift 2: 0b0000000000000010
    Shift 3: 0b0000000000000100
    ...
    Shift16: 0b1000000000000000

    Args:
      word: 16-bit value of the keyboard row-column crossing status.
      latch_shift: True to latch for each bit shift.
    """
    commands = []
    for i in range(15, -1, -1):
      commands.append((self._CONTROL.KEYBOARD_SHIFT_REGISTER_DATA,
                       'on' if (word & (1 << i)) else 'off'))
      commands.append((self._CONTROL.KEYBOARD_SHIFT_REGISTER_CLOCK, 'on'))
      commands.append((self._CONTROL.KEYBOARD_SHIFT_REGISTER_CLOCK, 'off'))
      if latch_shift:
        commands.append((self._CONTROL.KEYBOARD_SHIFT_REGISTER_LATCH, 'on'))
        commands.append((self._CONTROL.KEYBOARD_SHIFT_REGISTER_LATCH, 'off'))

    self._servo.MultipleSet(commands)
    self._LatchOutput()

  def SimulateKeystrokes(self):
    """Triggers all row-column crossings in sequence."""
    self._Emulate(1 << 15, True)
    self._Reset()
    self._LatchOutput()

  def KeyPress(self, bitmask, period_secs):
    """Emulates a key press in a specific period.

    Args:
      bitmask: 16-bit value will be output.
      period_secs: The bitmask will be kept for a specified period.
    """
    self._Emulate(bitmask, False)
    time.sleep(period_secs)
    self._Reset()
    self._LatchOutput()

