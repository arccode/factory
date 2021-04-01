# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests keyboard functionality.

Description
-----------
This test check basic keyboard functionality by asking operator to press each
keys on keyboard once at a time.

The layout of the keyboard is derived from vpd 'region' value, and can be
overwritten by argument ``layout``.

If ``allow_multi_keys`` is True, the operator can press multiple keys at once
to speed up the testing.

If ``sequential_press`` or ``strict_sequential_press`` is True, the operator
have to press each key in order from top-left to bottom-right. Additionally, if
``strict_sequential_press`` is True, the test would fail if the operator press
the wrong key.

A dict ``repeat_times`` can be specified to indicate number of times each key
have to be pressed before the key is marked as checked.

The test would fail after ``timeout_secs`` seconds.

Test Procedure
--------------
1. The test shows an image of the keyboard, and each key labeled with how many
   times it need to be pressed.
2. Operator press each key the number of times needed, and keys on UI would be
   marked as such.
3. The test pass when all keys have been pressed for the number of times
   needed, or fail after ``timeout_secs`` seconds.

Dependency
----------
Depends on 'evdev' module to monitor key presses.

Examples
--------
To test keyboard functionality, add this into test list::

  {
    "pytest_name": "keyboard"
  }

To test keyboard functionality, allow multiple keys to be pressed at once, and
have a timeout of 10 seconds, add this into test list::

  {
    "pytest_name": "keyboard",
    "args": {
      "allow_multi_keys": true,
      "timeout_secs": 10
    }
  }

To test keyboard functionality, ask operator to press keys in order, skip
keycode [4, 5, 6], have keycode 3 be pressed 5 times, and other keys be pressed
2 times to pass, add this into test list::

  {
    "pytest_name": "keyboard",
    "args": {
      "sequential_press": true,
      "skip_keycodes": [4, 5, 6],
      "repeat_times": {
        "3": 5,
        "default": 2
      }
    }
  }

To test keyboard functionality, ask operator to press keys in order (and fail
the test if wrong key is pressed), and set keyboard layout to ISO, add this
into test list::

  {
    "pytest_name": "keyboard",
    "args": {
      "strict_sequential_press": true,
      "layout": "ISO"
    }
  }
"""

import ast
import os
import re
import time

from cros.factory.test.l10n import regions
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test.utils import evdev_utils
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import schema

from cros.factory.external import evdev


_RE_EVTEST_EVENT = re.compile(
    r'^Event: time .*?, type .*? \((.*?)\), code (.*?) \(.*?\), value (.*?)$')

_POWER_KEY_CODE = 116

_INTEGER_STRING_SCHEMA = {
    'type': 'string',
    'pattern': r'^(0[Bb][01]+|0[Oo][0-7]+|0[Xx][0-9A-Fa-f]+|[1-9][0-9]*|0)$'
}
_REPLACEMENT_KEYMAP_SCHEMA = schema.JSONSchemaDict(
    'replacement_keymap schema object', {
        'type': 'object',
        'propertyNames': _INTEGER_STRING_SCHEMA,
        'patternProperties': {
            '^.*$': _INTEGER_STRING_SCHEMA
        }
    })

class KeyboardTest(test_case.TestCase):
  """Tests if all the keys on a keyboard are functioning. The test checks for
  keydown and keyup events for each key, following certain order if required,
  and passes if both events of all keys are received.

  Among the args are two related arguments:
  - sequential_press: a keycode is simply ignored if the key is not pressed
    in order
  - strict_sequential_press: the test failed immediately if a key is skipped.
  """
  ARGS = [
      Arg(
          'allow_multi_keys', bool, 'Allow multiple keys pressed '
          'simultaneously. (Less strictly checking '
          'with shorter cycle time)', default=False),
      Arg(
          'multi_keys_delay', (int, float), 'When ``allow_multi_keys`` is '
          '``False``, do not fail the test if the delay between the '
          'consecutivepresses is more than ``multi_keys_delay`` seconds.',
          default=0),
      Arg(
          'layout', str, 'Use specified layout other than derived from VPD. '
          'If None, the layout from the VPD is used.', default=None),
      Arg('timeout_secs', int, 'Timeout for the test.', default=30),
      Arg(
          'sequential_press', bool, 'Indicate whether keycodes need to be '
          'pressed sequentially or not.', default=False),
      Arg(
          'strict_sequential_press', bool, 'Indicate whether keycodes need to '
          'be pressed strictly sequentially or not.', default=False),
      Arg('board', str,
          'If presents, in filename, the board name is appended after layout.',
          default=''),
      Arg(
          'device_filter', (int, str),
          'If present, the input event ID or a substring of the input device '
          'name specifying which keyboard to test.', default=None),
      Arg('skip_power_key', bool, 'Skip power button testing', default=False),
      Arg('skip_keycodes', list, 'Keycodes to skip', default=[]),
      Arg(
          'replacement_keymap', dict, 'Dictionary mapping key codes to '
          'replacement keycodes. The keycodes must be a string of an integer'
          'since json does not support format like 0x10.', default={},
          schema=_REPLACEMENT_KEYMAP_SCHEMA),
      Arg(
          'detect_long_press', bool, 'Detect long press event. Usually for '
          'detecting bluetooth keyboard disconnection.', default=False),
      Arg(
          'repeat_times', dict, 'A dict object {key_code: times} to specify '
          'number of presses required for keys specified in key code, e.g. '
          '``{"28": 3, "57": 5}``, then ENTER (28) shall be pressed 3 times '
          'while SPACE (57) shall be pressed 5 times. If you want all keys to '
          'be pressed twice, you can do: ``{"default": 2}``. '
          'You can find keycode mappings in /usr/include/linux/input.h',
          default=None),
  ]

  def setUp(self):
    self.assertTrue(not (self.args.allow_multi_keys and
                         self.args.sequential_press),
                    'Sequential press requires one key at a time.')
    self.assertTrue(not (self.args.allow_multi_keys and
                         self.args.strict_sequential_press),
                    'Strict sequential press requires one key at a time.')
    self.assertTrue(self.args.multi_keys_delay >= 0,
                    'multi_keys_delay should be a positive number.')
    if self.args.allow_multi_keys and self.args.multi_keys_delay > 0:
      session.console.warning('multi_keys_delay is not effective when '
                              'allow_multi_keys is set to True.')

    # Get the keyboard input device.
    try:
      self.keyboard_device = evdev_utils.FindDevice(
          self.args.device_filter, evdev_utils.IsKeyboardDevice)
    except evdev_utils.MultipleDevicesFoundError:
      session.console.info(
          "Please set the test argument 'device_filter' to one of the name.")
      raise

    # Initialize keyboard layout and bindings
    self.layout = self.GetKeyboardLayout()
    if self.args.board:
      self.layout += '_%s' % self.args.board
    self.bindings = self.ReadBindings(self.layout)

    # Apply any replacement keymap
    if self.args.replacement_keymap:
      replacement_keymap = {
          int(key, 0): int(value, 0)
          for key, value in self.args.replacement_keymap.items()}
      new_bind = {key: value for key, value in self.bindings.items()
                  if key not in replacement_keymap}
      for old_key, new_key in replacement_keymap.items():
        new_bind[new_key] = self.bindings[old_key]
      self.bindings = new_bind

    self.all_keys = set(self.bindings.keys())

    self.frontend_proxy = self.ui.InitJSTestObject('KeyboardTest', self.layout,
                                                   self.bindings)

    keycodes_to_skip = set(self.args.skip_keycodes)
    if self.args.skip_power_key:
      keycodes_to_skip.add(_POWER_KEY_CODE)
    keycodes_to_skip &= self.all_keys

    if self.args.sequential_press or self.args.strict_sequential_press:
      self.key_order_list = [
          key for key in self.ReadKeyOrder(self.layout) if key in self.all_keys
      ]
    else:
      self.key_order_list = None
      self.ui.HideElement('instruction-sequential')

    if self.args.allow_multi_keys:
      self.ui.HideElement('instruction-single-key')

    self.down_keys = set()
    self.ignored_down_keys = set()
    self.last_press_time = 0

    self.number_to_press = {}
    repeat_times = self.args.repeat_times or {}
    default_number_to_press = repeat_times.get('default', 1)

    for key in self.all_keys:
      if key in keycodes_to_skip:
        self.number_to_press[key] = 0
        self.MarkKeyState(key, 'skipped')
      else:
        self.number_to_press[key] = repeat_times.get(
            str(key), default_number_to_press)
        self.MarkKeyState(key, 'untested')

    self.dispatcher = evdev_utils.InputDeviceDispatcher(
        self.keyboard_device, self.event_loop.CatchException(self.HandleEvent))

    testlog.UpdateParam('malfunction_key',
                        description='The keycode of malfunction keys')

  def tearDown(self):
    """Terminates the running process or we'll have trouble stopping the test.
    """
    self.dispatcher.close()
    self.keyboard_device.ungrab()

  def GetKeyboardLayout(self):
    """Uses the given keyboard layout or auto-detect from VPD."""
    if self.args.layout:
      return self.args.layout

    # Use the primary keyboard_layout for testing.
    region = process_utils.CheckOutput(['vpd', '-g', 'region']).strip()
    return regions.REGIONS[region].keyboard_mechanical_layout

  def ReadBindings(self, layout):
    """Reads in key bindings and their associates figure regions."""
    bindings_filename = os.path.join(self.ui.GetStaticDirectoryPath(),
                                     layout + '.bindings')
    bindings = ast.literal_eval(file_utils.ReadFile(bindings_filename))
    for k in bindings:
      # Convert single tuple to list of tuples
      if not isinstance(bindings[k], list):
        bindings[k] = [bindings[k]]
    return bindings

  def ReadKeyOrder(self, layout):
    """Reads in key order that must be followed when press key."""
    key_order_list_filename = os.path.join(self.ui.GetStaticDirectoryPath(),
                                           layout + '.key_order')
    return ast.literal_eval(file_utils.ReadFile(key_order_list_filename))

  def MarkKeyState(self, keycode, state):
    """Call frontend JavaScript to update UI."""
    self.frontend_proxy.MarkKeyState(keycode, state,
                                     self.number_to_press[keycode])

  def HandleEvent(self, event):
    """Handler for evdev events."""
    if event.type != evdev.ecodes.EV_KEY:
      return
    if event.value == 1:
      self.OnKeydown(event.code)
    elif event.value == 0:
      self.OnKeyup(event.code)
    elif self.args.detect_long_press and event.value == 2:
      fail_msg = 'Got events on keycode %d pressed too long.' % event.code
      session.console.error(fail_msg)
      self.FailTask(fail_msg)

  def OnKeydown(self, keycode):
    """Callback when got a keydown event from evdev."""
    if keycode not in self.all_keys:
      return

    if (not self.args.allow_multi_keys and self.down_keys and
        time.time() - self.last_press_time < self.args.multi_keys_delay):
      self.FailTask(
          'Got key down event on keycode %d but there are other key pressed: %d'
          % (keycode, next(iter(self.down_keys))))

    if keycode in self.down_keys:
      self.FailTask('Got 2 key down events on keycode %d but didn\'t get key up'
                    'event.')

    self.last_press_time = time.time()

    if self.key_order_list and keycode in self.key_order_list:
      first_untested_key = next(
          key for key in self.key_order_list
          if self.number_to_press[key] > 0 and key not in self.down_keys)
      if keycode != first_untested_key:
        if self.args.strict_sequential_press:
          self.FailTask('Expect keycode %d but get %d' % (first_untested_key,
                                                          keycode))
        else:
          self.down_keys.add(keycode)
          self.ignored_down_keys.add(keycode)
          return

    self.down_keys.add(keycode)

    if self.number_to_press[keycode] > 0:
      self.MarkKeyState(keycode, 'down')

  def OnKeyup(self, keycode):
    """Callback when got a keyup event from evdev."""
    if keycode not in self.all_keys:
      return

    if keycode not in self.down_keys:
      self.FailTask(
          'Got key up event for keycode %d but did not get key down event' %
          keycode)
    self.down_keys.remove(keycode)

    if keycode in self.ignored_down_keys:
      self.ignored_down_keys.remove(keycode)
      return

    if self.number_to_press[keycode] > 0:
      self.number_to_press[keycode] -= 1
      if self.number_to_press[keycode] > 0:
        self.MarkKeyState(keycode, 'untested')
      else:
        self.MarkKeyState(keycode, 'tested')

    if all(num_left == 0 for num_left in self.number_to_press.values()):
      self.PassTask()

  def FailTestTimeout(self):
    """Fail the test due to timeout, and log untested keys."""
    failed_keys = [
        key for key, num_left in self.number_to_press.items() if num_left
    ]
    for failed_key in failed_keys:
      testlog.LogParam('malfunction_key', failed_key)
    self.FailTask('Keyboard test timed out. Malfunction keys: %r' % failed_keys)

  def runTest(self):
    self.keyboard_device.grab()
    self.dispatcher.StartDaemon()
    self.ui.StartCountdownTimer(self.args.timeout_secs, self.FailTestTimeout)
    self.WaitTaskEnd()
