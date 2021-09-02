# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import asyncore

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


def IsMouseDevice(dev):
  """Check if a device is a mouse device.

  Args:
    dev: evdev.InputDevice

  Returns:
    True if dev is a mouse device.
  """
  keycaps = dev.capabilities().get(evdev.ecodes.EV_KEY, [])
  return (evdev.ecodes.BTN_MOUSE in keycaps and
          evdev.ecodes.BTN_RIGHT in keycaps and
          evdev.ecodes.BTN_MIDDLE in keycaps)


class FindDeviceError(RuntimeError):
  """An exception from FindDevice."""

  def __init__(self, candidates, filtered_candidates) -> None:
    super().__init__()
    self.candidates = candidates
    self.filtered_candidates = filtered_candidates

  @staticmethod
  def FormatDevice(dev):
    return f'(path={dev.fn}, name={dev.name!r})'

  @staticmethod
  def FormatDevices(devices):
    return str(sorted(map(FindDeviceError.FormatDevice, devices)))

  def FormatFilteredCandidates(self):
    return str({
        key: self.FormatDevices(devices)
        for key, devices in self.filtered_candidates
        if devices
    })

  def __repr__(self) -> str:
    return '{}({})'.format(self.__class__.__name__, self.__str__())


class DeviceNotFoundError(FindDeviceError):
  """An exception which indicates there is no such device."""

  _message_template = "Can't find device. Filtered candidates: {}."

  def __str__(self) -> str:
    return self._message_template.format(self.FormatFilteredCandidates())


class MultipleDevicesFoundError(FindDeviceError):
  """An exception which indicates there are multiple such devices."""

  _message_template = ('Not having exactly one candidate! Left candidates: {}. '
                       'Filtered candidates: {}.')

  def __str__(self) -> str:
    return self._message_template.format(
        self.FormatDevices(self.candidates), self.FormatFilteredCandidates())


def FindDevice(*args):
  """Find a device that match all arguments.

  Args:
    Each argument should be None (skipped), int (event id), str (pattern to
    search in evdev name), or a filter function with domain evdev.InputDevice.

  Returns:
    An evdev.InputDevice
  """
  candidates = GetDevices()
  filtered_candidates = []

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
    filtered_candidates.append(
        (item,
         [candidate for candidate in candidates if not dev_filter(candidate)]))
    candidates = list(filter(dev_filter, candidates))

  if len(candidates) == 1:
    return candidates[0]
  if not candidates:
    raise DeviceNotFoundError(candidates, filtered_candidates)
  raise MultipleDevicesFoundError(candidates, filtered_candidates)


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
