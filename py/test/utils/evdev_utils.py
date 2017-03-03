# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import asyncore

import factory_common  # pylint: disable=unused-import
from cros.factory.external import evdev
from cros.factory.utils import process_utils


def GetDevices():
  """Gets all the input devices.

  Returns:
    A list of evdev.InputDevice() instances of the input devices.
  """
  return [evdev.InputDevice(d) for d in evdev.list_devices()]


def IsLidEventDevice(dev):
  """Check if a device is with EV_SW and SW_LID capabilities.

  Args:
    dev: evdev.InputDevice

  Returns:
    True if dev is a lid event device.
  """
  return evdev.ecodes.SW_LID in dev.capabilities().get(evdev.ecodes.EV_SW, [])


def IsKeyboardDevice(dev):
  """Check if a device is with EV_KEY and KEY_ENTER capabilities.

  Args:
    dev: evdev.InputDevice

  Returns:
    True if dev is a keyboard device.
  """
  return evdev.ecodes.KEY_ENTER in dev.capabilities().get(evdev.ecodes.EV_KEY,
                                                          [])


def SendKeys(key_sequence):
  """Sends the given key sequence through uinput.

  Args:
    key_sequence: A list of keys to send.  For the list of valid key events, see
        evdev.ecodes module.
  """
  uinput = evdev.UInput()
  for k in key_sequence:
    uinput.write(evdev.ecodes.EV_KEY, k, 1)
  for k in key_sequence:
    uinput.write(evdev.ecodes.EV_KEY, k, 0)
  uinput.syn()
  uinput.close()


def IsTouchDevice(dev):
  """Check if a device is a touch device.

  Args:
    dev: evdev.InputDevice

  Returns:
    True if dev is a touch device.
  """
  keycaps = dev.capabilities().get(evdev.ecodes.EV_KEY, [])
  return evdev.ecodes.BTN_TOUCH in keycaps


def IsStylusDevice(dev):
  """Check if a device is a stylus device.

  Args:
    dev: evdev.InputDevice

  Returns:
    True if dev is a stylus device.
  """
  keycaps = dev.capabilities().get(evdev.ecodes.EV_KEY, [])
  return bool(set(keycaps) & set([
      evdev.ecodes.BTN_STYLUS,
      evdev.ecodes.BTN_STYLUS2,
      evdev.ecodes.BTN_TOOL_PEN]))


def IsTouchpadDevice(dev):
  """Check if a device is a touchpad device.

  Args:
    dev: evdev.InputDevice

  Returns:
    True if dev is a touchpad device.
  """
  keycaps = dev.capabilities().get(evdev.ecodes.EV_KEY, [])
  return (evdev.ecodes.BTN_TOUCH in keycaps and
          evdev.ecodes.BTN_MOUSE in keycaps)


def IsTouchscreenDevice(dev):
  """Check if a device is a touchscreen device.

  Args:
    dev: evdev.InputDevice

  Returns:
    True if dev is a touchscreen device.
  """
  return (IsTouchDevice(dev) and
          not IsTouchpadDevice(dev) and
          not IsStylusDevice(dev))


def FindDevice(*args):
  """Find a device with hints of arguments.

  Args:
    Each argument should be None (skipped), int (event id), str (pattern to
    search in evdev name), or a filter function with domain evdev.InputDevice.

  Returns:
    An evdev.InputDevice
  """
  for item in args:
    if item is not None:
      if isinstance(item, int):
        return evdev.InputDevice('/dev/input/event%d' % item)
      if isinstance(item, str):
        # pylint: disable=cell-var-from-loop
        dev_filter = lambda dev: item in dev.name
      elif callable(item):
        dev_filter = item
      else:
        raise ValueError('Invalid argument %r' % item)
      candidates = [dev for dev in GetDevices() if dev_filter(dev)]
      assert len(candidates) == 1, 'Not having exactly one candidate!'
      return candidates[0]
  raise ValueError('Arguments are all None.')


class InputDeviceDispatcher(asyncore.file_dispatcher):
  """Extends asyncore.file_dispatcher to read input device."""

  def __init__(self, device, event_handler):
    self.device = device
    self.event_handler = event_handler
    asyncore.file_dispatcher.__init__(self, device)

  def recv(self, ign=None):
    del ign  # Unused.
    return self.device.read()

  def handle_read(self):
    for event in self.recv():
      self.event_handler(event)

  def writable(self):
    return False

  def StartDaemon(self):
    """Start a daemon thread forwarding events to event_handler."""
    process_utils.StartDaemonThread(target=asyncore.loop)
