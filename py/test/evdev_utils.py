# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import asyncore
import evdev


def GetDevices():
  """Gets all the input devices.

  Returns:
    A list of evdev.InputDevice() instances of the input devices.
  """
  return [evdev.InputDevice(d) for d in evdev.list_devices()]


def GetKeyboardDevices():
  """Gets the keyboard device.

  Looks for devices with EV_KEY capabilities and with a KEY_ENTER.

  Returns:
    A list of evdev.InputDevice() instances of the keyboard devices.
  """
  return [d for d in GetDevices()
          if (evdev.ecodes.EV_KEY in d.capabilities().iterkeys() and
              evdev.ecodes.KEY_ENTER in d.capabilities()[evdev.ecodes.EV_KEY])]


def GetTouchDevices():
  """Gets the touch devices.

  Looks for devices with EV_KEY capabilities and with a BTN_TOUCH.

  Returns:
    A list of evdev.InputDevice() instances of the touch devices.
  """
  return [d for d in GetDevices()
          if (evdev.ecodes.EV_KEY in d.capabilities().iterkeys() and
              evdev.ecodes.BTN_TOUCH in d.capabilities()[evdev.ecodes.EV_KEY])]


def GetTouchpadDevices():
  """Gets the touchpad devices.

  Looks for touch devices with BTN_MOUSE.

  Returns:
    A list of evdev.InputDevice() instances of the touchpad devices.
  """
  return [d for d in GetTouchDevices()
          if evdev.ecodes.BTN_MOUSE in d.capabilities()[evdev.ecodes.EV_KEY]]


def GetTouchscreenDevices():
  """Gets the touchscreen devices.

  Looks for touch devices without BTN_MOUSE.

  Returns:
    A list of evdev.InputDevice() instances of the touchscreen devices.
  """
  return [d for d in GetTouchDevices()
          if evdev.ecodes.BTN_MOUSE not in
          d.capabilities()[evdev.ecodes.EV_KEY]]


class InputDeviceDispatcher(asyncore.file_dispatcher):
  """Extends asyncore.file_dispatcher to read input device."""
  def __init__(self, device, event_handler):
    self.device = device
    self.event_handler = event_handler
    asyncore.file_dispatcher.__init__(self, device)

  def recv(self, ign=None): # pylint:disable=W0613
    return self.device.read()

  def handle_read(self):
    for event in self.recv():
      self.event_handler(event)
