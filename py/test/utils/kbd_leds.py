#!/usr/bin/env python2

# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Routines to modify keyboard LED state."""

import ast
import fcntl
import logging
import os
import sys
import threading


# Constants from /usr/include/linux/kd.h.
KDSETLED = 0x4B32
LED_SCR = 1
LED_NUM = 2
LED_CAP = 4

# Resets LEDs to the default values (console_ioctl.h says that any higher-
# order bit than LED_CAP will do).
LED_RESET = 8

# Number of VTs on which to set the keyboard LEDs.
MAX_VTS = 8

# Set of FDs of all TTYs on which to set LEDs.  Lazily initialized by SetLeds.
_tty_fds = None
_tty_fds_lock = threading.Lock()


def SetLeds(state):
  """Sets the current LEDs on VTs [0,MAX_VTS) to the given state.

  Errors are ignored.
  (We set the LED on all VTs because /dev/console may not work reliably under
  the combination of X and autotest.)

  Args:
    pattern: A bitwise OR of zero or more of LED_SCR, LED_NUM, and LED_CAP.

  Returns:
    True if able to set at least one LED, and False otherwise.
  """
  global _tty_fds  # pylint: disable=global-statement
  with _tty_fds_lock:
    if _tty_fds is None:
      _tty_fds = []
      for tty in xrange(MAX_VTS):
        dev = '/dev/tty%d' % tty
        try:
          _tty_fds.append(os.open(dev, os.O_RDWR))
        except Exception:
          logging.exception('Unable to open %s', dev)

  if not _tty_fds:
    return False

  for fd in _tty_fds:
    try:
      fcntl.ioctl(fd, KDSETLED, state)
    except Exception:
      pass

  return True


class Blinker(object):
  """Blinks LEDs asynchronously according to a particular pattern.

  Start() and Stop() are not thread-safe and must be invoked from the same
  thread.

  This can also be used as a context manager:

      with leds.Blinker(...):
          ...do something that will take a while...
  """
  thread = None

  def __init__(self, pattern):
    """Constructs the blinker (but does not start it).

    Args:
      pattern: A list of tuples.  Each element is (state, duration),
          where state contains the LEDs that should be lit (a bitwise
          OR of LED_SCR, LED_NUM, and/or LED_CAP).  For example,

              ((LED_SCR|LED_NUM|LED_CAP, .2),
               (0, .05))

          would turn all LEDs on for .2 s, then all off for 0.05 s,
          ad infinitum.
    """
    self.pattern = pattern
    self.done = threading.Event()

  def Start(self):
    """Starts blinking in a separate thread until Stop is called.

    May only be invoked once.
    """
    assert not self.thread
    self.thread = threading.Thread(target=self._Run)
    self.thread.start()

  def Stop(self):
    """Stops blinking."""
    self.done.set()
    if self.thread:
      self.thread.join()
      self.thread = None

  def __enter__(self):
    self.Start()

  def __exit__(self, exc_type, exc_value, traceback):
    del exc_type, exc_value, traceback  # Unused.
    self.Stop()

  def _Run(self):
    while True:  # Repeat pattern forever
      for state, duration in self.pattern:
        if not SetLeds(state):
          return  # Failure, end this thread
        self.done.wait(duration)
        if self.done.is_set():
          SetLeds(LED_RESET)
          return


def main():
  """Blinks the pattern in sys.argv[1] if present, or the famous theme from
  William Tell otherwise.
  """
  if len(sys.argv) > 1:
    blinker = Blinker(ast.literal_eval(sys.argv[1]))
  else:
    DURATION_SCALE = .125

    def Blip(state, duration=1):
      return [(state, duration * .6 * DURATION_SCALE),
              (0, duration * .4 * DURATION_SCALE)]

    blinker = Blinker(
        2 * (2 * Blip(LED_NUM) + Blip(LED_NUM, 2)) + 2 * Blip(LED_NUM) +
        Blip(LED_CAP, 2) + Blip(LED_SCR, 2) + Blip(LED_CAP | LED_SCR, 2) +
        2 * Blip(LED_NUM) + Blip(LED_NUM, 2) + 2 * Blip(LED_NUM) +
        Blip(LED_CAP, 2) + 2 * Blip(LED_SCR) + Blip(LED_CAP, 2) +
        Blip(LED_NUM, 2) + Blip(LED_CAP | LED_NUM, 2)
    )

  with blinker:
    # Wait for newline, and then quit gracefully
    sys.stdin.readline()


if __name__ == '__main__':
  main()
