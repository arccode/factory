# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import asyncore

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import process_utils

from cros.factory.external import evdev


def GetDevices():
  """Gets all the input devices.

  Returns:
    A list of evdev.InputDevice() instances of the input devices.
  """
  return [evdev.InputDevice(d) for d in evdev.list_devices()]

def FilterEvdevEcodes(dev, cnf):
  """Check if the capabilities of the device satisfy that of the CNF

  Args:
    dev: evdev.InputDevice
    cnf: list of lists of evdev.ecodes

  Returns:
    True if dev satisfies cnf
  """
  caps = set(dev.capabilities().get(evdev.ecodes.EV_KEY, []))
  for clause in cnf:
    if set(clause) & caps == set():
      return False
  return True

def IsLidEventDevice(dev):
  """Check if a device is with EV_SW and SW_LID capabilities.

  Args:
    dev: evdev.InputDevice

  Returns:
    True if dev is a lid event device.
  """
  return evdev.ecodes.SW_LID in dev.capabilities().get(evdev.ecodes.EV_SW, [])


def IsTabletEventDevice(dev):
  """Check if a device is with EV_SW and SW_TABLET_MODE capabilities.

  Args:
    dev: evdev.InputDevice

  Returns:
    True if dev is a tablet event device.
  """
  return evdev.ecodes.SW_TABLET_MODE in dev.capabilities().get(
      evdev.ecodes.EV_SW, [])


def IsKeyboardDevice(dev):
  """Check if a device is with EV_KEY and KEY_ENTER capabilities.

  Args:
    dev: evdev.InputDevice

  Returns:
    True if dev is a keyboard device.
  """
  keys = {
      evdev.ecodes.KEY_ENTER,
      evdev.ecodes.KEY_LEFTCTRL,
      evdev.ecodes.KEY_LEFTALT
  }
  caps = set(dev.capabilities().get(evdev.ecodes.EV_KEY, []))
  return keys.issubset(caps)


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
  return FilterEvdevEcodes(dev, [[
      evdev.ecodes.BTN_STYLUS,
      evdev.ecodes.BTN_STYLUS2,
      evdev.ecodes.BTN_TOOL_PEN]])


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
  return (not IsTouchpadDevice(dev) and
          evdev.ecodes.ABS_MT_SLOT in dict(
              dev.capabilities().get(evdev.ecodes.EV_ABS, [])))


class DeviceNotFoundError(RuntimeError):
  pass


class MultipleDevicesFoundError(RuntimeError):
  pass


def FindDevice(*args):
  """Find a device that match all arguments.

  Args:
    Each argument should be None (skipped), int (event id), str (pattern to
    search in evdev name), or a filter function with domain evdev.InputDevice.

  Returns:
    An evdev.InputDevice
  """
  candidates = GetDevices()

  for item in args:
    # pylint: disable=cell-var-from-loop
    if item is None:
      continue
    if isinstance(item, int):
      dev_filter = lambda dev: dev.fn == '/dev/input/event%d' % item
    elif isinstance(item, str):
      if item in evdev.ecodes.__dict__:
        dev_filter = lambda dev: FilterEvdevEcodes(
            dev, [[evdev.ecodes.__dict__[item]]])
      else:
        dev_filter = lambda dev: item in dev.name
    elif callable(item):
      dev_filter = item
    else:
      raise ValueError('Invalid argument %r' % item)
    candidates = list(filter(dev_filter, candidates))

  if len(candidates) == 1:
    return candidates[0]
  elif not candidates:
    raise DeviceNotFoundError("Can't find device.")
  else:
    raise MultipleDevicesFoundError('Not having exactly one candidate!')


def DeviceReopen(dev):
  """Reopen a device so that the event buffer is cleared.

  Args:
    dev: evdev.InputDevice

  Returns:
    A different evdev.InputDevice of the same device but with empty event
    buffer.
  """
  return evdev.InputDevice(dev.fn)


class InputDeviceDispatcher(asyncore.file_dispatcher):
  """Extends asyncore.file_dispatcher to read input device."""

  def __init__(self, device, event_handler):
    self.device = device
    self.event_handler = event_handler
    asyncore.file_dispatcher.__init__(self, device)

  def handle_read(self):
    # Spec - https://docs.python.org/2/library/asyncore.html mentions about
    # that recv() may raise socket.error with EAGAIN or EWOULDBLOCK, even
    # though select.select() or select.poll() has reported the socket ready
    # for reading.
    #
    # We have the similar issue here; the buffer might be still empty when
    # reading from an input device even though asyncore calls handle_read().
    # As a result, we call read_one() here because it will return None when
    # buffer is empty. On the other hand, if we call read() and iterate the
    # returned generator object then an IOError - EAGAIN might be thrown but
    # this behavior is not documented so can't leverage on it.
    while True:
      event = self.device.read_one()
      if event is None:
        break

      self.event_handler(event)

  def writable(self):
    return False

  def StartDaemon(self):
    """Start a daemon thread forwarding events to event_handler."""
    process_utils.StartDaemonThread(target=asyncore.loop)
