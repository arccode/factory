# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""
A factory test to test the functionality of keyboard.

dargs:
  layout: Use specified layout other than derived from VPD. (default: get from
      VPD)
  keyboard_device_name: Device name of keyboard. (default: 'AT Translated Set 2
      keyboard')
  timeout_secs: Timeout for the test. (default: 30 seconds)
  sequential_press (optional): Indicate whether keycodes need to be
      pressed sequentially or not.
"""

import asyncore
import evdev
import os
import re
import unittest

from cros.factory.l10n import regions
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.countdown_timer import StartCountdownTimer
from cros.factory.test.ui_templates import OneSection
from cros.factory.test.utils import StartDaemonThread
from cros.factory.utils.process_utils import CheckOutput


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
    '.keyboard-test-keyup { background-color: green; opacity: 0.5; }\n')

_POWER_KEY_CODE = 116


class InputDeviceDispatcher(asyncore.file_dispatcher):
  def __init__(self, device, event_handler):
    self.device = device
    self.event_handler = event_handler
    asyncore.file_dispatcher.__init__(self, device)

  def recv(self, ign=None): # pylint:disable=W0613
    return self.device.read()

  def handle_read(self):
    for event in self.recv():
      self.event_handler(event)

class KeyboardTest(unittest.TestCase):
  """Tests if all the keys on a keyboard are functioning. The test checks for
  keydown and keyup events for each key, following certain order if required,
  and passes if both events of all keys are received.
  """
  ARGS = [
    Arg('layout', (str, unicode), 'Use specified layout other than derived '
        'from VPD.', default=None, optional=True),
    Arg('keyboard_device_name', (str, unicode), 'Device name of keyboard.',
        default='AT Translated Set 2 keyboard'),
    Arg('timeout_secs', int, 'Timeout for the test.', default=30),
    Arg('sequential_press', bool, 'Indicate whether keycodes need to be '
        'pressed sequentially or not.', default=False, optional=True),
    Arg('board', str,
        'If presents, in filename, the board name is appended after layout. ',
        default=''),
    Arg('skip_power_key', bool, 'Skip power button testing', default=False),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_KEYBOARD_TEST_DEFAULT_CSS)

    # Initialize keyboard layout and bindings
    self.layout = self.GetKeyboardLayout()
    if self.args.board:
      self.layout += '_%s' % self.args.board
    self.bindings = self.ReadBindings(self.layout)
    if self.args.skip_power_key:
      self.bindings.pop(_POWER_KEY_CODE)

    self.key_order_list = None
    if self.args.sequential_press:
      self.key_order_list = self.ReadKeyOrder(self.layout)

    # Initialize frontend presentation
    self.template.SetState(_HTML_KEYBOARD)
    self.ui.CallJSFunction('setUpKeyboardTest', self.layout, self.bindings,
                           _ID_IMAGE, self.key_order_list)

    self.dispatchers = []
    self.EnableXKeyboard(False)
    StartDaemonThread(target=self.MonitorEvdevEvent)
    StartCountdownTimer(self.args.timeout_secs,
                        lambda: self.ui.CallJSFunction('failTest'),
                        self.ui,
                        _ID_COUNTDOWN_TIMER)

  def tearDown(self):
    """Terminates the running process or we'll have trouble stopping the
    test.
    """
    for dispatcher in self.dispatchers:
      dispatcher.close()
    self.EnableXKeyboard(True)

  def GetKeyboardLayout(self):
    """Uses the given keyboard layout or auto-detect from VPD."""
    kml_mapping = dict((x.keyboard, x.keyboard_mechanical_layout)
                       for x in regions.REGIONS.itervalues())
    if self.args.layout:
      return self.args.layout
    vpd_layout = CheckOutput(['vpd', '-g', 'keyboard_layout']).strip()
    if vpd_layout:
      return kml_mapping[vpd_layout]
    else:
      return 'ANSI'

  def ReadBindings(self, layout):
    """Reads in key bindings and their associates figure regions."""
    bindings = None
    base = os.path.splitext(os.path.realpath(__file__))[0] + '_static'
    bindings_filename = os.path.join(base, layout + '.bindings')
    with open(bindings_filename, 'r') as f:
      bindings = eval(f.read())
    for k in bindings:
      # Convert single tuple to list of tuples
      if not isinstance(bindings[k], list):
        bindings[k] = [bindings[k],]
    return bindings

  def ReadKeyOrder(self, layout):
    """Reads in key order that must be followed when press key."""
    key_order_list = None
    base = os.path.splitext(os.path.realpath(__file__))[0] + '_static'
    key_order_list_filename = os.path.join(base, layout + '.key_order')
    with open(key_order_list_filename, 'r') as f:
      key_order_list = eval(f.read())
    return key_order_list

  def EnableXKeyboard(self, enable):
    """Enables/Disables keyboard at the X server."""
    CheckOutput(['xinput', 'set-prop', self.args.keyboard_device_name,
                 'Device Enabled', '1' if enable else '0'])

  def MonitorEvdevEvent(self):
    """Monitors keyboard events from evdev."""
    for dev in map(evdev.InputDevice, evdev.list_devices()):
      if evdev.ecodes.EV_KEY in dev.capabilities().iterkeys():
        self.dispatchers.append(InputDeviceDispatcher(dev, self.HandleEvent))
    asyncore.loop()

  def HandleEvent(self, event):
    if event.type == evdev.ecodes.EV_KEY:
      if event.value == 1:
        self.MarkKeydown(event.code)
      elif event.value == 0:
        self.MarkKeyup(event.code)

  def MarkKeydown(self, keycode):
    """Calls Javascript to mark the given keycode as keydown."""
    if not keycode in self.bindings:
      return True
    self.ui.CallJSFunction('markKeydown', keycode)

  def MarkKeyup(self, keycode):
    """Calls Javascript to mark the given keycode as keyup."""
    if not keycode in self.bindings:
      return True
    self.ui.CallJSFunction('markKeyup', keycode)

  def runTest(self):
    self.ui.Run()
