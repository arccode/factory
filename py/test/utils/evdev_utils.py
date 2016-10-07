# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import asyncore

import factory_common  # pylint: disable=W0611

from cros.factory.external import evdev


def GetDevices():
  """Gets all the input devices.

  Returns:
    A list of evdev.InputDevice() instances of the input devices.
  """
  return [evdev.InputDevice(d) for d in evdev.list_devices()]


def GetLidEventDevices():
  """Gets lid event devices.

  Looks for devices with EV_SW capabilities and with a SW_LID.

  Returns:
    A list of evdev.InputDevice() instances of lid event devices.
  """
  return [d for d in GetDevices()
          if (evdev.ecodes.EV_SW in d.capabilities().iterkeys() and
              evdev.ecodes.SW_LID in d.capabilities()[evdev.ecodes.EV_SW])]


def GetKeyboardDevices():
  """Gets the keyboard device.

  Looks for devices with EV_KEY capabilities and with a KEY_ENTER.

  Returns:
    A list of evdev.InputDevice() instances of the keyboard devices.
  """
  return [d for d in GetDevices()
          if (evdev.ecodes.EV_KEY in d.capabilities().iterkeys() and
              evdev.ecodes.KEY_ENTER in d.capabilities()[evdev.ecodes.EV_KEY])]


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


def GetTouchDevices():
  """Gets the touch devices.

  Looks for touch devices.

  Returns:
    A list of evdev.InputDevice() instances of the touch devices.
  """
  return [d for d in GetDevices() if IsTouchDevice(d)]


def GetStylusDevices():
  """Gets the stylus devices.

  Looks for stylus devices.

  Returns:
    A list of evdev.InputDevice() instances of the stylus devices.
  """
  return [d for d in GetDevices() if IsStylusDevice(d)]


def GetTouchpadDevices():
  """Gets the touchpad devices.

  Looks for touchpad devices.

  Returns:
    A list of evdev.InputDevice() instances of the touchpad devices.
  """
  return [d for d in GetDevices() if IsTouchpadDevice(d)]


def GetTouchscreenDevices():
  """Gets the touchscreen devices.

  Looks for touchscreen devices.

  Returns:
    A list of evdev.InputDevice() instances of the touchscreen devices.
  """
  return [d for d in GetDevices() if IsTouchscreenDevice(d)]


class InputDeviceDispatcher(asyncore.file_dispatcher):
  """Extends asyncore.file_dispatcher to read input device."""

  def __init__(self, device, event_handler):
    self.device = device
    self.event_handler = event_handler
    asyncore.file_dispatcher.__init__(self, device)

  def recv(self, ign=None):  # pylint:disable=W0613
    return self.device.read()

  def handle_read(self):
    for event in self.recv():
      self.event_handler(event)

  def writable(self):
    return False
