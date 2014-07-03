# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Emulates keyboard scan."""

# standard python libs
import time


class KeyboardEmulator(object):
  """Controls keyboard emulator in Whale fixture.

  Keyboard emulator provides two methods: one is to trigger all row-column
  crossings in sequence; the other is to emulate pressing of single or
  multiple key(s) for a specified period.
  """

  def __init__(self, servo):
    """Constructor."""
    self._servo = servo
    self._reset()
    self._latch_output()

  def _latch_output(self):
    """Outputs 16 GPIOs from the 2 shift registers."""
    self._servo.whale_kb_shfg_latch = 'on'
    self._servo.whale_kb_shfg_latch = 'off'

  def _reset(self):
    """Resets the 2 shift registers."""
    self._servo.whale_kb_shfg_rst = 'on'
    self._servo.whale_kb_shfg_rst = 'off'

  def _emulate(self, word, latch_shift):
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
    for i in range(15, -1, -1):
      self._servo.whale_kb_shfg_data = 'on' if (word & (1 << i)) else 'off'

      self._servo.whale_kb_shfg_clk = 'on'
      self._servo.whale_kb_shfg_clk = 'off'

      if latch_shift:
        self._latch_output()

    self._latch_output()

  def SimulateKeystrokes(self):
    """Triggers all row-column crossings in sequence."""
    self._emulate(1 << 15, True)
    self._reset()
    self._latch_output()

  def KeyPress(self, bitmask, period_secs):
    """Emulates a key press in a specific period.

    Args:
      bitmask: 16-bit value will be output.
      period_secs: The bitmask will be kept for a specified period.
    """
    self._emulate(bitmask, False)
    time.sleep(period_secs)
    self._reset()
    self._latch_output()
