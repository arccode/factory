# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re
import threading

from cros.factory.device import device_types
from cros.factory.utils import process_utils
from cros.factory.utils.type_utils import Enum

from cros.factory.external import pyudev


class UdevMonitorBase(device_types.DeviceComponent):
  """Abstract class for detecting udev event.

  This class provide an interface to detect udev event, e.g.
  insertion / removal of an USB disk / SD card.

  Caller can use
  :py:func:`cros.factory.device.udev.UdevMonitorBase.RequestUpdate`
  to start monitoring a given sysfs path, and call
  :py:func:`cros.factory.device.udev.UdevMonitorBase.RemoveUpdate` to stop
  monitoring.

  Implementation of this class should override
  :py:func:`cros.factory.device.udev.OnStartMonitor` and
  :py:func:`cros.factory.device.udev.OnStopMonitor`, which is executed when
  caller requests / removes update. The child is also responsible for calling
  :py:func:`cros.factory.device.udev.UdevMonitorBase.NotifyEvent to send out the
  event.
  """

  # Event types.
  Event = Enum(['INSERT', 'REMOVE'])

  def __init__(self, dut):
    super(UdevMonitorBase, self).__init__(dut)
    self._handler = {}
    self._SYS_BLOCK_PATH = self._device.path.join('/sys', 'block')
    self._DEV_BLOCK_PATH = '/dev'

  def StartMonitorPath(self, sys_path, handler):
    """Reqeust update of the given sysfs path.

    Args:
      sys_path: The expected sysfs path that udev events should
          come from, e.g., /sys/devices/pci0000:00/0000:00:1a.0/usb1/1-1/1-1.2.
          The path could be a regular expression.
      handler: The callback function to be executed when event triggered.
          Should have signature handler(event, device), where event should be
          cros.factory.device.udev.UdevMonitorBase.Event and device should be
          instance of cros.factory.device.udev.UdevMonitorBase.Device. This
          callback function may be executed in another thread, so it should be
          thread-safe.
    """

    if sys_path not in self._handler:
      self._handler[sys_path] = handler
      if len(self._handler) == 1:
        self.OnStartMonitor()

  def StopMonitorPath(self, sys_path):
    """Remove update of the given sysfs path.

    Args:
      sys_path: The sysfs path that would be removed from udev events update.
          The path could be a regular expression.
    """

    if sys_path in self._handler:
      del self._handler[sys_path]
      if not self._handler:
        self.OnStopMonitor()

  def GetPathUnderMonitor(self):
    """Get the list of the sysfs paths that is currently under monitoring."""
    return list(self._handler)

  def NotifyEvent(self, event, sys_path, device):
    """Execute the callback function related to the given sysfs path.

    The child is responsible for calling this function when there is new udev
    event happens.

    Args:
      event: Udev event.
      sys_path: The sysfs path that is requested for update.
      device: Instance of cros.factory.device.udev.UdevMonitorBase.Device.
    """
    handler = self._handler[sys_path]
    if handler is not None:
      # We don't want slow handler to block our event detecting. Run the handler
      # in another worker thread.
      process_utils.StartDaemonThread(target=handler, args=(event, device))

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

  def GetSysBlockPath(self):
    """Get tye sysfs block device folder, e.g. /sys/block.

    The default implementation returns /sys/block. Child can override this
    function to provide different path.
    """
    return self._SYS_BLOCK_PATH

  def GetDevBlockPath(self):
    """The folder to find the block device to read / write.

    The default implementation returns /dev. Child can override this function to
    provide different path.
    """
    return self._DEV_BLOCK_PATH

  class Device:
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
  """Implementation of UdevMonitorBase using pyudev.


  This class is an implementation of
  :py:class:`cros.factory.device.udev.UdevMonitorBase`
  using pyudev to monitoring the udev event happen in the local device.
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
      if self._device.path.exists(device.device_node):
        action = self._UDEV_ACTION_INSERT
      else:
        action = self._UDEV_ACTION_REMOVE

    event = self._EVENT_MAP.get(action)
    if event is None:
      # Unrelated events that we don't want to process.
      return

    for path in self.GetPathUnderMonitor():
      if re.match(path, device.sys_path):
        self.NotifyEvent(event, path, device)


class PollingUdevMonitor(UdevMonitorBase):
  """Implementation of UdevMonitorBase polling sysfs folder.

  This class implements :py:class:`cros.factory.device.udev.UdevMonitorBase` by
  polling block device under sysfs block folder, e.g. /sys/block, which can be
  used when there is no udevadm on the dut.

  When a new device is inserted, a new file will be created in sysfs block
  device folder, e.g.  /sys/block, and the file should be a symbolic link to the
  true sysfs path. This calss monitor new events by polling the folder and
  examing the symbolic link.
  """

  _PERIOD = 1

  def __init__(self, dut):
    super(PollingUdevMonitor, self).__init__(dut)
    self._running = False
    self._devices = {}
    self._timer = None
    # Cache for realpath.
    self._realpaths = {}

  def OnStartMonitor(self):
    # Clear the cache.
    self._realpaths = {}
    # Scan for the current devices.
    self._devices = self._Scan()
    self._running = True
    self._timer = threading.Timer(self._PERIOD, self._Polling)
    self._timer.start()

  def OnStopMonitor(self):
    if self._timer:
      self._timer.cancel()
    self._running = False

  def _Scan(self):
    device = {}
    # We only scan for storage devices, e.g., sd* and mmc*.
    sys_block_path = self.GetSysBlockPath()
    block_devs = (
        self._device.Glob(self._device.path.join(sys_block_path, 'sd*')) +
        self._device.Glob(self._device.path.join(sys_block_path, 'mmc*')))

    # New cache for realpath.
    curr_realpaths = {}

    for block_dev in block_devs:
      real_path = self._realpaths.get(block_dev)
      if not real_path:
        real_path = self._device.path.realpath(block_dev)
      curr_realpaths[block_dev] = real_path
      # TODO(chenghan): This doesn't work with regex sys_path monitored, but
      #                 currently this class is not used anywhere so it should
      #                 be fine.
      sys_paths = [path for path in self.GetPathUnderMonitor() if
                   real_path.startswith(path)]
      for sys_path in sys_paths:
        node = self._device.path.join(
            self.GetDevBlockPath(), self._device.path.basename(block_dev))
        device[sys_path] = self.Device(node, real_path)
    self._realpaths = curr_realpaths
    return device

  def _Polling(self):
    if not self._running:
      return

    curr_devices = self._Scan()
    for sys_path in set(curr_devices.keys()) - set(self._devices.keys()):
      self.NotifyEvent(self.Event.INSERT, sys_path, curr_devices[sys_path])

    for sys_path in set(self._devices.keys()) - set(curr_devices.keys()):
      self.NotifyEvent(self.Event.REMOVE, sys_path, self._devices[sys_path])

    self._devices = curr_devices
    self._timer = threading.Timer(self._PERIOD, self._Polling)
    self._timer.start()
