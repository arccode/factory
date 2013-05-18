#!/usr/bin/python -u
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Filters keys in X.

It is used to consume and discard shortcut keys listed in _GRAB_KEYS.
It has two classes: KeyFilterImpl and KeyFilter. KeyFilter is a launcher
that runs/spawns this executable as a standalone process. KeyFilterImpl
is the actual implementation of key filter.

Usage:
  Standalone process: ./key_filter.py
  Fork a subprocess in a Python code:
    key_filter = KeyFilter()
    key_filter.Start()  # non-blocking
    ...
    # when done...
    key_filter.Stop()
"""

import argparse
import collections
import logging
import signal

# Guard loading Xlib because it is currently not available in the
# image build process host-depends list. Failure to load in
# production should always manifest during regular use.
try:
  from Xlib import X, XK  # pylint: disable=F0401
  from Xlib.display import Display  # pylint: disable=F0401
  _has_Xlib = True
except:  # pylint: disable=W0702
  _has_Xlib = False

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.utils.process_utils import Spawn

Keystroke = collections.namedtuple('Keystroke', ['mod', 'key'])

def InitGrabKeys(grab_keys):
  """Initializes a list of keys to be grabbed.

  Args:
    keys: a list to store Keystroke to be grabbed.
  """
  if not _has_Xlib:
    logging.error('Python Xlib module does not exist.')
    return

  del grab_keys[:]

  # Search, tab, and function keys (back, forward, reload, etc.)
  # with any modifiers.
  grab_keys.extend([
      Keystroke(X.AnyModifier, k) for k in (
          'Super_L Tab F1 F2 F3 F4 F5 F6 F7 F8 F9 F10'.split())])

  # Ctrl+?
  grab_keys.extend([
      Keystroke(X.ControlMask, k) for k in (
          'N T O Q W T Tab P S R plus minus 0 D F G K E Return U M '
          'H J question L 1 2 3 4 5 6 7 8 9'). split()])

  # Ctrl+Shift+?
  grab_keys.extend([
      Keystroke(X.ControlMask | X.ShiftMask, k) for k in (
          'N Q W T Tab L R D G I J B').split()])

  # Alt+?
  grab_keys.extend([
      Keystroke(X.Mod1Mask, k) for k in (
          '1 2 3 4 5 6 7 8 9 Tab Return E F D').split()])

  # Alt+Shift+?
  grab_keys.extend([
      Keystroke(X.Mod1Mask | X.ShiftMask, k) for k in (
          'Tab B T S').split()])

  # Ctrl+Alt+?
  grab_keys.extend([
      Keystroke(X.ControlMask | X.Mod1Mask, 'question'),
      Keystroke(X.ControlMask | X.Mod1Mask, 'Z')])


class KeyFilterImpl(object):
  """Filters specific keypress events.

  It consumes and discards certain keypress events.

  Args:
    disp: X's Display() object.
    unmap_caps_lock: True to unmap CapsLock key.
    caps_lock_keycode: Keycode for CapsLock.

  For some cases, we cannot get Caps_Lock keysyms value. So we ask for
  CapsLock keycode value here.
  TODO(deanliao): figure out why and fix it.
  """

  def __init__(self, disp, unmap_caps_lock=False, caps_lock_keycode=0,
               power_keycode=0):
    self._disp = disp
    self._disp.allow_events(X.AsyncKeyboard, X.CurrentTime)
    self._root = self._disp.screen().root
    self._root.change_attributes(event_mask=X.KeyPressMask)
    self._unmap_caps_lock = unmap_caps_lock
    self._grab_keys = []
    InitGrabKeys(self._grab_keys)
    if power_keycode:
      self._grab_keys.append(Keystroke(X.AnyModifier, power_keycode))

    if unmap_caps_lock:
      self._caps_lock_keycode = caps_lock_keycode
      if self._caps_lock_keycode:
        self._caps_lock_keymapping = self._disp.get_keyboard_mapping(
            self._caps_lock_keycode, 1)[0].tolist()

  def StringToKeycode(self, s):
    """Looks up a keycode for a keystroke.

    Args:
      s: keystroke name, e.g. 'Caps_Lock'.

    Returns:
      keycode. 0 if no found.
    """
    return self._disp.keysym_to_keycode(XK.string_to_keysym(s))

  def GrabKey(self, mod, key):
    """Grabs keypress event.

    Args:
      mod: modifier
      key: key (string. But can use integer to represent keycode)
    """
    logging.debug('GrabKey(mod:%d, key:%s)', mod, key)
    keycode = key if isinstance(key, int) else self.StringToKeycode(key)

    if keycode:
      self._root.grab_key(keycode, mod, 1, X.GrabModeAsync, X.GrabModeAsync)
    else:
      logging.error('Keycode not found for key: %s', key)

  def UngrabKey(self, mod, key):
    """Ungrabs keypress event.

    Args:
      mod: modifier
      key: key (string. But can use integer to represent keycode)
    """
    logging.debug('UngrabKey(mod:%d, key:%s)', mod, key)
    keycode = key if isinstance(key, int) else self.StringToKeycode(key)
    if keycode:
      self._root.ungrab_key(keycode, mod)

  def Run(self):
    """Starts filtering keys.

    It is a blocking call to set up keys to grab and to consume grabbed
    keypress event.
    """
    # A hack to disable CapsLock by clearing its key mapping.
    if self._unmap_caps_lock and self._caps_lock_keycode:
      self._disp.change_keyboard_mapping(
          self._caps_lock_keycode, [(0,) * len(self._caps_lock_keymapping)])

    for k in self._grab_keys:
      self.GrabKey(k.mod, k.key)

    try:
      while True:
        grabbed_event = self._disp.next_event()
        logging.debug('grabbed_event: %s', str(grabbed_event))
    except Exception as e:
      logging.error('Unable to grab key event: %s', str(e))

  def Terminate(self):
    """Stops filtering keys."""
    for k in self._grab_keys:
      self.UngrabKey(k.mod, k.key)

    # Restore CapsLock's key mapping.
    if self._unmap_caps_lock and self._caps_lock_keycode:
      self._disp.change_keyboard_mapping(self._caps_lock_keycode,
                                         self._caps_lock_keymapping)


class KeyFilter:
  """A launcher to run key filter in a sub-process.

  Args:
    unmap_caps_lock: True to unmap CapsLock key; default False.
    caps_lock_keycode: (int) Keycode of CapsLock; default 0.

  Usage:
    key_filter = KeyFilter()
    key_filter.Start()  # non-blocking
    ...
    # when done...
    key_filter.Stop()
  """
  def __init__(self, unmap_caps_lock=False, caps_lock_keycode=0):
    self._unmap_caps_lock = unmap_caps_lock
    self._caps_lock_keycode = caps_lock_keycode
    self._process = None

  def Start(self):
    cmd = [__file__.replace('.pyc', '.py')]
    if self._unmap_caps_lock:
      cmd.append('--unmap_caps_lock')
    if self._caps_lock_keycode:
      cmd.extend(['--caps_lock_keycode', str(self._caps_lock_keycode)])
    logging.debug('Spawn: %s', ' '.join(cmd))
    try:
      self._process = Spawn(cmd)
    except Exception as e:
      logging.error('Error running Spawn("%s"): %s', ' '.join(cmd), str(e))

  def Stop(self):
    if self._process:
      self._process.terminate()
      self._process.wait()


def main():
  parser = argparse.ArgumentParser(
      description='Filter ChromeOS shortcut keys.')
  parser.add_argument('--verbose', '-v',
                      action='store_true', help='Enable debug logging.')
  parser.add_argument('--unmap_caps_lock', action='store_true',
                      help='Unmap CapsLock key.')
  parser.add_argument('--caps_lock_keycode', type=int, default=66,
                      help='CapsLock keycode; default 66.')
  # Not every platform defines keysym for power button. Let's assign keycode
  # here.
  parser.add_argument('--power_keycode', type=int, default=124,
                      help='Power button keycode; default 124.')
  args = parser.parse_args()

  factory.init_logging('key_filter', verbose=args.verbose)

  key_filter_impl = KeyFilterImpl(Display(),
                                  unmap_caps_lock=args.unmap_caps_lock,
                                  caps_lock_keycode=args.caps_lock_keycode,
                                  power_keycode=args.power_keycode)
  signal.signal(signal.SIGTERM, lambda signum, frame: key_filter_impl.Terminate)
  key_filter_impl.Run()

if __name__ == '__main__':
  main()
