# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''
Tools for sending out "ectool" commands
'''

import logging
import os
import re
import time


KEYMATRIX = {'0': (6, 8), '1': (6, 1), '2': (6, 4), '3': (6, 2), '4': (6, 3),
             '5': (3, 3), '6': (3, 6), '7': (6, 6), '8': (6, 5), '9': (6, 9),
             'a': (4, 1), 'b': (0, 3), 'c': (5, 2), 'd': (4, 2), 'e': (7, 2),
             'f': (4, 3), 'g': (1, 3), 'h': (1, 6), 'i': (7, 5), 'j': (4, 6),
             'k': (4, 5), 'l': (4, 9), 'm': (5, 6), 'n': (0, 6), 'o': (7, 9),
             'p': (7, 8), 'q': (7, 1), 'r': (7, 3), 's': (4, 4), 't': (2, 3),
             'u': (7, 6), 'v': (5, 3), 'w': (7, 4), 'x': (5, 4), 'y': (2, 6),
             'z': (5, 1), ' ': (5, 11), ',': (5, 5), '-': (3, 8), '.': (5, 9),
             '/': (5, 8), ';': (4, 8), '=': (0, 8), '[': (2, 8), '\'': (1, 8),
             '\\': (3, 11), ']': (2, 5),'`': (3, 1), '\n': (4, 11),
             '<alt_l>': (6, 10), '<alt_r>': (0, 10), '<backspace>': (1, 11),
             '<ctrl_l>': (2, 0), '<ctrl_r>': (4, 0), '<down>': (6, 11),
             '<enter>': (4, 11), '<esc>': (1, 1), '<f1>': (0, 2),
             '<f2>': (3, 2), '<f3>': (2, 2), '<f4>': (1, 2), '<f5>': (3, 4),
             '<f6>': (2, 4), '<f7>': (1, 4), '<f8>': (2, 9), '<f9>': (1, 9),
             '<f10>': (0, 4), '<left>': (7, 12), '<right>': (6, 12),
             '<search>': (0, 1), '<space>': (5, 11), '<shift_l>': (5, 7),
             '<shift_r>': (7, 7), '<tab>': (2, 1), '<up>': (7, 11)}


class ECToolCommand(object):
  def KeyConvert(self, key):
    return KEYMATRIX[key] if isinstance(key, str) else key

  def KeyDown(self, key):
    os.system('ectool kbpress %d %d 1' % self.KeyConvert(key))

  def KeyUp(self, key):
    os.system('ectool kbpress %d %d 0' % self.KeyConvert(key))

  def KeyPress(self, key, duration=0.1):
    logging.info('Press %s', key)
    self.KeyDown(key)
    time.sleep(duration)
    self.KeyUp(key)

  def PressString(self, key_string, duration=0.1, interval=0.1):
    key_list = re.findall('[^<>]|<.*?>', key_string)
    for key in key_list:
      self.KeyPress(key, duration)
      time.sleep(interval)

  def PressAllKeys(self, duration=0.1, interval=0.1):
    for key in set(KEYMATRIX.values()):
      self.KeyPress(key, duration)
      time.sleep(interval)

  def TurnOffAllUSBPower(self):
    os.system('ectool usbchargemode 0 0')
    os.system('ectool usbchargemode 1 0')

  def TurnOnAllUSBPower(self):
    os.system('ectool usbchargemode 0 3')
    os.system('ectool usbchargemode 1 3')
