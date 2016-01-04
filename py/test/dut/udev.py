# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import pyudev

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component
from cros.factory.utils.type_utils import Enum


class UdevMonitorBase(component.DUTComponent):
  """Abstract class for detecting udev event.

  This class provide an interface to detect udev event, e.g.
  insertion / removal of an USB disk / SD card.

  Caller can use :py:func:`cros.factory.test.dut.udev.UdevMonitorBase.RequestUpdate`
  to start monitoring a given sysfs path, and call
  :py:func:`cros.factory.test.dut.udev.UdevMonitorBase.RemoveUpdate` to stop monitoring.

  Implementation of this class should override
  :py:func:`cros.factory.test.dut.udev.OnStartMonitor` and
  :py:func:`cros.factory.test.dut.udev.OnStopMonitor`, which is executed when caller
  requests / removes update. The child is also responsible for calling
  :py:func:`cros.factory.test.dut.udev.UdevMonitorBase.NotifyEvent to send out the event.
  """

  # Event types.
  Event = Enum(['INSERT', 'REMOVE'])

  def __init__(self, dut):
    super(UdevMonitorBase, self).__init__(dut)
    self._handler = {}

  def StartMonitorPath(self, sys_path, handler):
    """Reqeust update of the given sysfs path.

    Args:
      sys_path: The expected sysfs path that udev events should
          come from, e.g., /sys/devices/pci0000:00/0000:00:1a.0/usb1/1-1/1-1.2
      handler: The callback function to be executed when event triggered. Should have signature
          handler(event, device), where event should be cros.test.dut.udev.UdevMonitorBase.Event
          and device should be instance of cros.test.dut.udev.UdevMonitorBase.Device. This callback
          function may be executed in another thread, so it should be thread-safe.
    """

    if sys_path not in self._handler:
      self._handler[sys_path] = handler
      if len(self._handler) == 1:
        self.OnStartMonitor()

  def StopMonitorPath(self, sys_path):
    """Remove update of the given sysfs path.

    Args:
      sys_path: The sysfs path that would be removed from udev events update.
    """

    if sys_path in self._handler:
      del self._handler[sys_path]
      if not self._handler:
        self.OnStopMonitor()

  def GetPathUnderMonitor(self):
    """Get the list of the sysfs paths that is currently under monitoring."""
    return self._handler.keys()[:]

  def NotifyEvent(self, event, sys_path, device):
    """Execute the callback function related to the given sysfs path.

    The child is responsible for calling this function when there is new udev event happens.

    Args:
      event: Udev event.
      sys_path: The sysfs path that is requested for update.
      device: Instance of cros.factory.test.dut.udev.UdevMonitorBase.Device.
    """
    handler = self._handler[sys_path]
    if handler is not None:
      handler(event, device)

  def OnStartMonitor(self):
    """Callback function when system starts monitoring the udev device.

    This function is called when caller calls RequestUpdate for monitoring.
    """
    raise NotImplementedError

  def OnStopMonitor(self):
    """Callback function when system stops monitoring the udev device.

    This function is called when all requests are removed.
    """
    raise NotImplementedError

  class Device(object):
    """The device object."""

    def __init__(self, device_node, sys_path):
      """Constructor of Device object.

      Args:
        device_node: The true path of the device node, e.g., /dev/sda.
        sys_path: The sysfs path of the deivce.
      """
      self.device_node = device_node
      self.sys_path = sys_path


class LocalUdevMonitor(UdevMonitorBase):
  """Implementation of :py:class:`cros.factory.test.dut.udev.UdevMonitorBase` using pyudev.

  This class use pyudev to monitoring the udev event happen in the local device.
  """

  # udev constants
  _UDEV_ACTION_INSERT = 'add'
  _UDEV_ACTION_REMOVE = 'remove'
  _UDEV_ACTION_CHANGE = 'change'

  _EVENT_MAP = {_UDEV_ACTION_INSERT: UdevMonitorBase.Event.INSERT,
                _UDEV_ACTION_REMOVE: UdevMonitorBase.Event.REMOVE}

  def __init__(self, dut):
    super(LocalUdevMonitor, self).__init__(dut)
    self._udev_observer = None
    context = pyudev.Context()
    self._monitor = pyudev.Monitor.from_netlink(context)
    self._monitor.filter_by(subsystem='block', device_type='disk')
    self._udev_observer = None

  def OnStartMonitor(self):
    self._udev_observer = pyudev.MonitorObserver(self._monitor,
                                                 self._HandleUdevEvent)
    self._udev_observer.start()

  def OnStopMonitor(self):
    self._udev_observer.stop()

  def _HandleUdevEvent(self, action, device):
    """The udev event handler.

    Args:
      action: The udev action to handle.
      device: A device object.
    """
    # Try to determine the change event is an insert or remove.
    if action == self._UDEV_ACTION_CHANGE:
      if self._dut.FileExists(device.device_node):
        action = self._UDEV_ACTION_INSERT
      else:
        action = self._UDEV_ACTION_REMOVE

    event = self._EVENT_MAP.get(action)
    if event is None:
      # Unrelated events that we don't want to process.
      return

    for path in self.GetPathUnderMonitor():
      if device.sys_path.startswith(path):
        self.NotifyEvent(event, path, device)

