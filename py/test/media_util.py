# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import commands
import logging
import os
import pyudev
import shutil
import tempfile
import threading

# udev constants
_UDEV_ACTION_INSERT = 'add'
_UDEV_ACTION_REMOVE = 'remove'


class _PyudevThread(threading.Thread):
  """Monitoring udev events in the background.

  This is a temporary class to asynchronously monitor udev events. Because only
  the new version of pyudev module provides asynchronous observer, the version
  we currently use does not. We can deprecate this class after the module has
  been upgraded.

  Note that due to pyudev's limited functionality. This thread won't stop once
  it has been started. Thus setting this thread to daemon is necessary. And of
  course we can not really stop receiving udev events, either. So the only way
  to pretend stop monitoring is to ignore all the events in the callback
  function.

  Usage example:
    pyudev_thread = _PyudevThread(UdevEventCallback,
                                  subsystem='block',
                                  device_type='disk')
    pyudev_thread.daemon = True
    pyudev_thread.start()
  """

  def __init__(self, callback, **udev_filters):
    """Constructor.

    Args:
      callback: Function to invoke when receiving udev events.
      udev_filters: Will be pass to pyudev.Monitor.filter_by(). Please refer to
          pyudev's doc to see what kind of filters it provides.
    """
    threading.Thread.__init__(self)
    self._callback = callback
    self._udev_filters = dict(udev_filters)

  def run(self):
    """Create an infinite loop to monitor udev events and invoke callbacks."""
    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(**self._udev_filters)
    for action, device in monitor:
      self._callback(action, device)


class MediaMonitor(object):
  """A wrapper to monitor media events.

  This class offers an easy way to monitor the insertion and removal
  activities of media devices.

  Attributes:
    on_insert: Function to invoke when receiving USB insert event.
        None means ignoring the event.
    on_remove: Function to invoke when receiving USB remove event.
        None means ignoring the event.
    is_monitoring: Bool indicating whether it's monitoring or not.

  Usage example:
    monitor = MediaMonitor()
    monitor.Start(on_insert=on_insert, on_remove=on_remove)
    monitor.Stop()
  """
  def __init__(self, subsystem='block'):
    self.on_insert = None
    self.on_remove = None
    self.is_monitoring = False
    self._observer = None
    self._pyudev_thread = None
    self._subsystem = subsystem

  def _UdevEventCallback(self, action, device):
    if self.is_monitoring == False:
      return
    if action == _UDEV_ACTION_INSERT:
      logging.info("Device inserted: %s", device.device_node)
      if self.on_insert:
        self.on_insert(device.device_node)
    elif action == _UDEV_ACTION_REMOVE:
      logging.info('Device removed: %s', device.device_node)
      if self.on_remove:
        self.on_remove(device.device_node)

  def Start(self, on_insert, on_remove):
    if self.is_monitoring:
      raise Exception("Multiple start() call is not allowed")
    self.on_insert = on_insert
    self.on_remove = on_remove
    # Setup the media monitor,
    # TODO(littlecvr): Use pyudev.MonitorObserver instead of writing our
    #                  own observer (PyudevThread) after pyudev module has
    #                  been upgraded. The right code is here, just uncomment
    #                  them and delete lines related to PyudevThread.
    # context = pyudev.Context()
    # monitor = pyudev.Monitor.from_netlink(context)
    # monitor.filter_by(subsystem='block', device_type='disk')
    # self._observer = pyudev.MonitorObserver(monitor, self._UdevEventCallback)
    # self._observer.start()
    if self._pyudev_thread == None:
      self._pyudev_thread = _PyudevThread(self._UdevEventCallback,
                                          subsystem=self._subsystem,
                                          device_type='disk')
      self._pyudev_thread.daemon = True
      self._pyudev_thread.start()
    self.is_monitoring = True
    logging.info("Start monitoring media actitivities.")

  def Stop(self):
    # TODO(littlecvr): Use pyudev.MonitorObserver instead of writing our
    #                  own observer (PyudevThread) after pyudev module has
    #                  been upgraded. The right code is here, just uncomment
    #                  them and delete lines related to PyudevThread.
    # self._observer.stop()

    # Due to pyudev's limited functionality. We can't really stop here. So we
    # simply set is_monitoring to False and ignore any event in the calback to
    # pretend we have stopped. This problem should be fixed after pyudev has
    # been upgraded.
    self.is_monitoring = False
    logging.info("Stop monitoring media actitivities.")


class MountedMedia(object):
  """A context manager to automatically mount and unmount specified device.

  Usage example:
    To mount the third partition of /dev/sda.

    with MountedMedia('/dev/sda', 3) as media_path:
      print("Mounted at %s." % media_path)
  """

  def __init__(self, dev_path, partition=None):
    """Constructs a context manager to automatically mount/umount.

    Args:
      dev_path: The absolute path to the device.
      partition: A optional number indicated which partition of the device
                 should be mounted. If None is given, the dev_path will be
                 the mounted partition.
    Returns:
      A MountedMedia instance with initialized proper path.

    Example:
      with MountedMedia('/dev/sdb', 1) as path:
        with open(os.path.join(path, 'test'), 'w') as f:
          f.write('test')
    """
    self._mount_dir = None
    self._mounted = False
    if partition is None:
      self._dev_path = dev_path
      return

    if dev_path[-1].isdigit():
      # Devices enumerated in numbers (ex, mmcblk0).
      self._dev_path = '%sp%d' % (dev_path, partition)
    else:
      # Devices enumerated in alphabets (ex, sda)
      self._dev_path = '%s%d' % (dev_path, partition)

    # For devices not using partition table (floppy mode),
    # allow using whole device as first partition.
    if (not os.path.exists(self._dev_path)) and (partition == 1):
      logging.info('Using device without partition table - %s', dev_path)
      self._dev_path = dev_path

  def __enter__(self):
    self._MountMedia()
    return self._mount_dir

  def __exit__(self, exc_type, exc_value, traceback):
    if self._mounted:
      self._UmountMedia()

  def _MountMedia(self):
    """Mount a partition of media at temporary directory.

    Exceptions are throwed if anything goes wrong.
    """
    # Create an temporary mount directory to mount.
    self._mount_dir = tempfile.mkdtemp(prefix='MountedMedia')
    logging.info("Media mount directory created: %s", self._mount_dir)
    exit_code, output = commands.getstatusoutput(
        'mount %s %s' % (self._dev_path, self._mount_dir))
    if exit_code != 0:
      shutil.rmtree(self._mount_dir)
      raise Exception("Failed to mount. Message-%s" % output)
    self._mounted = True

  def _UmountMedia(self):
    """Umounts the partition of the media."""
    # Umount media and delete the temporary directory.
    exit_code, output = commands.getstatusoutput(
        'umount %s' % self._mount_dir)
    if exit_code != 0:
      raise Exception("Failed to umount. Message-%s" % output)
    shutil.rmtree(self._mount_dir)
    self._mounted = False
