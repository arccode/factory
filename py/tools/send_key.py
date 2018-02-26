#!/usr/bin/env python
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Simulates an X keypress."""

import argparse

# pylint: disable=import-error
from Xlib.display import Display
from Xlib.ext import xtest
from Xlib import X
from Xlib import XK


def main():
  parser = argparse.ArgumentParser(
      description='Simulates an X keypress.')
  parser.add_argument('keysym', metavar='KEYSYM',
                      help='X keysym to simulate (e.g., "Tab")')
  args = parser.parse_args()

  display = Display()
  keysym = XK.string_to_keysym(args.keysym)
  if not keysym:
    parser.error('Unknown keysym %r' % args.keysym)
  keycode = display.keysym_to_keycode(keysym)

  xtest.fake_input(display, X.KeyPress, keycode)
  xtest.fake_input(display, X.KeyRelease, keycode)
  display.sync()


if __name__ == '__main__':
  main()
