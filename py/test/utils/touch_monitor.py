# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides classes that can get and maintain the state of
single-touch and multi-touch type B devices.

For multi-touch protocol, please refer to
https://kernel.org/doc/Documentation/input/multi-touch-protocol.txt

Quick Start:

  class MyMonitor(touch_monitor.MultiTouchMonitor):
    def OnNew(self, slot_id):
      slot = self.GetState().slots[slot_id]
      print slot.x, slot.y

  device = evdev_utils.FindDevice(evdev_utils.IsTouchscreenDevice)
  device.grab()
  monitor = MyMonitor(device)
  dispatcher = evdev_utils.InputDeviceDispatcher(device, monitor.Handler)
  dispatcher.StartDaemon()
  ...
  dispatcher.close()
  device.ungrab()
"""

import copy
import fcntl
import struct


# pylint: disable=no-name-in-module
from cros.factory.external.evdev import ecodes


class TouchMonitorBase:
  """Touch device monitor.

  Properties:
    device: evdev.InputDevice, the touch device it monitors.
  """

  class State:
    """Touch device state.

    Properties:
      keys: A dict of key states. ({BTN_LEFT, BTN_TOUCH, ...} -> {True, False})
    """
    def __init__(self):
      self.keys = {}

  def __init__(self, device):
    """Fetch the state of `device` and initialize.

    Args:
      device: evdev.InputDevice, the touch device to monitor.
    """

    def IoctlEVIOCGKEY():
      # This function calls ioctl with EVIOCGKEY request, which returns a bit
      # array. Each bit represents if a corresponding key is pressed or not.
      KEY_CNT = 0x2ff + 1  # Defined in <uapi/linux/input-event-codes.h>.
      nbytes = (KEY_CNT + 7) // 8
      # Defined in <uapi/linux/input.h>.
      EVIOCGKEY = (2 << 30) | (ord('E') << 8) | 0x18 | (nbytes << 16)
      in_buf = '\0' * nbytes
      out_buf = struct.unpack('=%dB' % nbytes,
                              fcntl.ioctl(device.fileno(), EVIOCGKEY, in_buf))
      return {key: bool((out_buf[key >> 3] >> (key & 7)) & 1)
              for key in caps[ecodes.EV_KEY]}

    self._device = device
    caps = device.capabilities()
    self._absinfos = dict(caps[ecodes.EV_ABS])
    self._state = self.State()
    self._state.keys = IoctlEVIOCGKEY()

    self._abs_queue = None
    self._key_down_queue = None
    self._key_up_queue = None
    self._ResetQueue()

  def _ResetQueue(self):
    # There is no specific order between EV_ABS events and EV_KEY events,
    # so we storage events in three queues with different priorities.
    # Process order: key down events -> ABS events -> key up events.
    self._abs_queue = []
    self._key_down_queue = []
    self._key_up_queue = []

  def _GetNormalizer(self, abs_event_code):
    # Returns a function that maps value in [absinfo.min, absinfo.max] to
    # [0, 1].
    absinfo = self._absinfos[abs_event_code]
    offset = absinfo.min
    scale = 1 / (absinfo.max - absinfo.min)
    return lambda value: min(max(0.0, (value - offset) * scale), 1.0)

  @property
  def device(self):
    return self._device

  def GetState(self):
    """Returns a copy of asynchronous device state."""
    return copy.deepcopy(self._state)

  def Handler(self, event):
    """Handles an event.

    Args:
      event: evdev.InputEvent
    """
    if event.type == ecodes.EV_ABS:
      self._abs_queue.append(event)
    elif event.type == ecodes.EV_KEY:
      if event.value != 0:
        self._key_down_queue.append(event)
      else:
        self._key_up_queue.append(event)
    elif event.type == ecodes.EV_SYN:
      self._HandleKEY(self._key_down_queue)
      self._HandleABS(self._abs_queue)
      self._HandleKEY(self._key_up_queue)
      self._ResetQueue()

  def _HandleABS(self, event_queue):
    pass

  def _HandleKEY(self, event_queue):
    for event in event_queue:
      self._state.keys[event.code] = bool(event.value)
      self.OnKey(event.code)

  def OnKey(self, key_event_code):
    """Called by Handler after state of a key changed."""


class SingleTouchMonitor(TouchMonitorBase):
  """Single-Touch device monitor.

  Properties:
    device: evdev.InputDevice, the single-touch device it monitors.
  """

  class State(TouchMonitorBase.State):
    """Single-Touch device state.

    Properties:
      keys: A dict of key states.
      x: float, normalized x coordinate in [0, 1].
      y: float, normalized y coordinate in [0, 1].
    """
    def __init__(self):
      super(SingleTouchMonitor.State, self).__init__()
      self.x = 0.0
      self.y = 0.0

  def __init__(self, device):
    """Fetch the state of `device` and initialize.

    Args:
      device: evdev.InputDevice, the single-touch device to monitor.
    """
    super(SingleTouchMonitor, self).__init__(device)
    self._normalize_x = self._GetNormalizer(ecodes.ABS_X)
    self._normalize_y = self._GetNormalizer(ecodes.ABS_Y)
    self._state.x = self._normalize_x(self._absinfos[ecodes.ABS_X].value)
    self._state.y = self._normalize_y(self._absinfos[ecodes.ABS_Y].value)

  def _HandleABS(self, event_queue):
    moved = False
    for event in event_queue:
      if event.code == ecodes.ABS_X:
        self._state.x = self._normalize_x(event.value)
        moved = True
      elif event.code == ecodes.ABS_Y:
        self._state.y = self._normalize_y(event.value)
        moved = True
    if moved:
      self.OnMove()

  def OnMove(self):
    """Called by Handler after X or Y coordinate changes."""


class MultiTouchMonitor(TouchMonitorBase):
  """Multi-Touch device monitor.

  Properties:
    device: evdev.InputDevice, the multi-touch device it monitors.
  """

  class MultiTouchSlot:
    """Multi-Touch slot.

    Properties:
      x: float, normalized x coordinate in [0, 1].
      y: float, normalized y coordinate in [0, 1].
      tid: Tracking id.
    """
    def __init__(self, x, y, tid):
      self.x = x
      self.y = y
      self.tid = tid

  class State(TouchMonitorBase.State):
    """Multi-Touch device state.

    Properties:
      keys: A dict of key states.
      slots: A list of MultiTouchSlot.
      num_fingers: Number of slots activating now.
    """
    def __init__(self):
      super(MultiTouchMonitor.State, self).__init__()
      self.slots = []
      self.num_fingers = 0

  def __init__(self, device):
    """Fetch the state of `device` and initialize.

    Args:
      device: evdev.InputDevice, the multi-touch device to monitor.
    """

    def IoctlEVIOCGMTSLOTS(code):
      # This function calls ioctl with EVIOCGMTSLOTS request, which can return
      # the X position, Y position, or tracking id of all slots as an array of
      # 32-bit signed integers. See <uapi/linux/input.h> for details.
      fmt = '=%di' % (1 + num_slots)
      nbytes = struct.calcsize(fmt)
      # Defined in <uapi/linux/input.h>.
      EVIOCGMTSLOTS = (2 << 30) | (ord('E') << 8) | 0x0a | (nbytes << 16)
      in_buf = struct.pack(fmt, code, *([0] * num_slots))
      out_buf = fcntl.ioctl(device.fileno(), EVIOCGMTSLOTS, in_buf)
      return struct.unpack(fmt, out_buf)[1:]

    super(MultiTouchMonitor, self).__init__(device)
    self._normalize_x = self._GetNormalizer(ecodes.ABS_MT_POSITION_X)
    self._normalize_y = self._GetNormalizer(ecodes.ABS_MT_POSITION_Y)
    num_slots = self._absinfos[ecodes.ABS_MT_SLOT].max + 1
    self._slot_id = self._absinfos[ecodes.ABS_MT_SLOT].value
    xs = [self._normalize_x(value)
          for value in IoctlEVIOCGMTSLOTS(ecodes.ABS_MT_POSITION_X)]
    ys = [self._normalize_y(value)
          for value in IoctlEVIOCGMTSLOTS(ecodes.ABS_MT_POSITION_Y)]
    tids = IoctlEVIOCGMTSLOTS(ecodes.ABS_MT_TRACKING_ID)
    self._state.slots = [MultiTouchMonitor.MultiTouchSlot(*t)
                         for t in zip(xs, ys, tids)]
    self._state.num_fingers = num_slots - tids.count(-1)

  def _HandleABS(self, event_queue):
    callback = None
    for event in event_queue:
      if event.code == ecodes.ABS_MT_SLOT:
        if callable(callback):
          callback(self._slot_id)  # pylint: disable=not-callable
          callback = None
        self._slot_id = event.value
      elif event.code == ecodes.ABS_MT_POSITION_X:
        self._state.slots[self._slot_id].x = self._normalize_x(event.value)
        if not callback:
          callback = self.OnMove
      elif event.code == ecodes.ABS_MT_POSITION_Y:
        self._state.slots[self._slot_id].y = self._normalize_y(event.value)
        if not callback:
          callback = self.OnMove
      elif event.code == ecodes.ABS_MT_TRACKING_ID:
        self._state.slots[self._slot_id].tid = event.value
        if event.value >= 0:
          self._state.num_fingers += 1
          callback = self.OnNew
        else:
          self._state.num_fingers -= 1
          callback = self.OnLeave
    if callback:
      callback(self._slot_id)

  def OnNew(self, slot_id):
    """Called by Handler after a new contact comes."""

  def OnMove(self, slot_id):
    """Called by Handler after a contact moved."""

  def OnLeave(self, slot_id):
    """Called by Handler after a contact leaves."""
