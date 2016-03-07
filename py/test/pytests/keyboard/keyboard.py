# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests keyboard functionality."""

from __future__ import print_function

import ast
import asyncore
import evdev
import logging
import os
import re
import unittest

import factory_common   # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.countdown_timer import StartCountdownTimer
from cros.factory.test.l10n import regions
from cros.factory.test.ui_templates import OneSection
from cros.factory.test.utils import evdev_utils
from cros.factory.utils.process_utils import CheckOutput
from cros.factory.utils.process_utils import StartDaemonThread


_RE_EVTEST_EVENT = re.compile(
    r'^Event: time .*?, type .*? \((.*?)\), code (.*?) \(.*?\), value (.*?)$')

_ID_IMAGE = 'keyboard-test-image'
_ID_COUNTDOWN_TIMER = 'keyboard-test-timer'
_HTML_KEYBOARD = (
    '<div id="%s" style="position: relative"></div>\n<div id="%s"></div>\n' %
    (_ID_IMAGE, _ID_COUNTDOWN_TIMER))

_KEYBOARD_TEST_DEFAULT_CSS = (
    '#keyboard-test-timer { font-size: 2em; }\n'
    '.keyboard-test-key-untested { display: none; }\n'
    '.keyboard-test-keydown { background-color: yellow; opacity: 0.5; }\n'
    '.keyboard-test-keyup { background-color: green; opacity: 0.5; }\n'
    '.keyboard-test-key-skip { background-color: gray; opacity: 0.5; }\n')

_POWER_KEY_CODE = 116


class KeyboardTest(unittest.TestCase):
  """Tests if all the keys on a keyboard are functioning. The test checks for
  keydown and keyup events for each key, following certain order if required,
  and passes if both events of all keys are received.

  Among the args are two related arguments:
  - sequential_press: a keycode is simply ignored if the key is not pressed
    in order
  - strict_sequential_press: the test failed immediately if a key is skipped.
  """
  ARGS = [
      Arg('allow_multi_keys', bool, 'Allow multiple keys pressed '
          'simultaneously. (Less strictly checking '
          'with shorter cycle time)', default=False),
      Arg('layout', (str, unicode),
          ('Use specified layout other than derived from VPD. '
           'If None, the layout from the VPD is used.'),
          default=None, optional=True),
      Arg('timeout_secs', int, 'Timeout for the test.', default=30),
      Arg('sequential_press', bool, 'Indicate whether keycodes need to be '
          'pressed sequentially or not.', default=False, optional=True),
      Arg('strict_sequential_press', bool, 'Indicate whether keycodes need to '
          'be pressed strictly sequentially or not.',
          default=False, optional=True),
      Arg('board', str,
          'If presents, in filename, the board name is appended after layout.',
          default=''),
      Arg('name_fragment', str, 'If present, a substring of the input device '
          'name specifying which keyboard to test.',
          default=None, optional=True),
      Arg('skip_power_key', bool, 'Skip power button testing', default=False),
      Arg('skip_keycodes', list, 'Keycodes to skip', default=[]),
      Arg('replacement_keymap', dict, 'Dictionary mapping key codes to '
          'replacement key codes', default={}),
      Arg('detect_long_press', bool, 'Detect long press event. Usually for '
          'detecting bluetooth keyboard disconnection.', default=False)
  ]

  def setUp(self):
    self.assertTrue(not (self.args.allow_multi_keys and
                         self.args.sequential_press),
                    'Sequential press requires one key at a time.')
    self.assertTrue(not (self.args.allow_multi_keys and
                         self.args.strict_sequential_press),
                    'Strict sequential press requires one key at a time.')

    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_KEYBOARD_TEST_DEFAULT_CSS)

    # Get the keyboard input device.
    keyboard_devices = evdev_utils.GetKeyboardDevices()
    if self.args.name_fragment:
      device_matcher = lambda k: self.args.name_fragment in k.name
      keyboard_devices = filter(device_matcher, keyboard_devices)
    assert len(keyboard_devices) >= 1, 'No matching keyboards detected.'
    assert len(keyboard_devices) <= 1, 'Multiple keyboards detected.'
    self.keyboard_device = keyboard_devices[0]

    # Initialize keyboard layout and bindings
    self.layout = self.GetKeyboardLayout()
    if self.args.board:
      self.layout += '_%s' % self.args.board
    self.bindings = self.ReadBindings(self.layout)

    # Apply any replacement keymap
    for old_key, new_key in self.args.replacement_keymap.iteritems():
      if old_key in self.bindings:
        self.bindings[new_key] = self.bindings[old_key]
        del self.bindings[old_key]

    keycodes_to_skip_dict = dict((k, True) for k in self.args.skip_keycodes)
    if self.args.skip_power_key:
      keycodes_to_skip_dict[_POWER_KEY_CODE] = True

    self.key_order_list = None
    if self.args.sequential_press or self.args.strict_sequential_press:
      self.key_order_list = self.ReadKeyOrder(self.layout)

    self.key_down = set()
    # Initialize frontend presentation
    self.template.SetState(_HTML_KEYBOARD)
    # Note that self.bindings and keycodes_to_skip_dict have integer keys,
    # but JavaScript will receive them as string keys, due to JSON conversion
    self.ui.CallJSFunction('setUpKeyboardTest', self.layout, self.bindings,
                           keycodes_to_skip_dict, _ID_IMAGE,
                           self.key_order_list,
                           self.args.strict_sequential_press,
                           self.args.allow_multi_keys)

    self.dispatchers = []
    self.keyboard_device.grab()
    StartDaemonThread(target=self.MonitorEvdevEvent)
    StartCountdownTimer(self.args.timeout_secs,
                        lambda: self.ui.CallJSFunction('failTestTimeout'),
                        self.ui,
                        _ID_COUNTDOWN_TIMER)

  def tearDown(self):
    """Terminates the running process or we'll have trouble stopping the test.
    """
    for dispatcher in self.dispatchers:
      dispatcher.close()
    self.keyboard_device.ungrab()

  def GetKeyboardLayout(self):
    """Uses the given keyboard layout or auto-detect from VPD."""
    if self.args.layout:
      return self.args.layout

    # Use the primary keyboard_layout for testing.
    region = CheckOutput(['vpd', '-g', 'region']).strip()
    return regions.REGIONS[region].keyboard_mechanical_layout

  def ReadBindings(self, layout):
    """Reads in key bindings and their associates figure regions."""
    bindings = None
    base = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), 'static')
    bindings_filename = os.path.join(base, layout + '.bindings')
    with open(bindings_filename, 'r') as f:
      bindings = ast.literal_eval(f.read())
    for k in bindings:
      # Convert single tuple to list of tuples
      if not isinstance(bindings[k], list):
        bindings[k] = [bindings[k]]
    return bindings

  def ReadKeyOrder(self, layout):
    """Reads in key order that must be followed when press key."""
    key_order_list = None
    base = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), 'static')
    key_order_list_filename = os.path.join(base, layout + '.key_order')
    with open(key_order_list_filename, 'r') as f:
      key_order_list = ast.literal_eval(f.read())
    return key_order_list

  def MonitorEvdevEvent(self):
    """Monitors keyboard events from evdev."""
    self.dispatchers.append(
        evdev_utils.InputDeviceDispatcher(
            self.keyboard_device, self.HandleEvent))
    asyncore.loop()

  def HandleEvent(self, event):
    if event.type == evdev.ecodes.EV_KEY:
      if event.value == 1:
        self.MarkKeydown(event.code)
      elif event.value == 0:
        self.MarkKeyup(event.code)
      elif self.args.detect_long_press and event.value == 2:
        fail_msg = 'Got events on keycode %d pressed too long.' % event.code
        factory.console.error(fail_msg)
        self.ui.CallJSFunction('failTest', fail_msg)

  def MarkKeydown(self, keycode):
    """Calls Javascript to mark the given keycode as keydown."""
    if not keycode in self.bindings:
      return True
    logging.debug('Get key down %d', keycode)
    # Fails the test if got two key pressed at the same time.
    if not self.args.allow_multi_keys and len(self.key_down):
      fail_msg = ('Got key down event on keycode %d but there are other keys '
                  'pressed: %s' % (keycode, self.key_down))
      factory.console.error(fail_msg)
      self.ui.CallJSFunction('failTest', fail_msg)
    self.ui.CallJSFunction('markKeydown', keycode)
    self.key_down.add(keycode)

  def MarkKeyup(self, keycode):
    """Calls Javascript to mark the given keycode as keyup."""
    if not keycode in self.bindings:
      return True
    if keycode not in self.key_down:
      fail_msg = ('Got key up event for keycode %d '
                  'but did not get key down event' % keycode)
      factory.console.error(fail_msg)
      self.ui.CallJSFunction('failTest', fail_msg)
    else:
      self.key_down.remove(keycode)
    self.ui.CallJSFunction('markKeyup', keycode)

  def runTest(self):
    self.ui.Run()
