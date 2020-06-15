# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import shutil
import subprocess
import tempfile

from cros.factory.external import pyudev

# udev constants
_UDEV_ACTION_INSERT = 'add'
_UDEV_ACTION_REMOVE = 'remove'


class MediaMonitor:
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
    monitor = MediaMonitor('block', 'disk')
    monitor.Start(on_insert=on_insert, on_remove=on_remove)
    monitor.Stop()
  """

  def __init__(self, subsystem, device_type):
    self.on_insert = None
    self.on_remove = None
    self.is_monitoring = False
    self._observer = None
    self._subsystem = subsystem
    self._device_type = device_type

  def _UdevEventCallback(self, action, device):
    if self.is_monitoring is False:
      return
    if action == _UDEV_ACTION_INSERT:
      logging.info('Device inserted: %s', device.device_node)
      if self.on_insert:
        self.on_insert(device)
    elif action == _UDEV_ACTION_REMOVE:
      logging.info('Device removed: %s', device.device_node)
      if self.on_remove:
        self.on_remove(device)

  def Start(self, on_insert, on_remove):
    if self.is_monitoring:
      raise Exception('Multiple start() call is not allowed')
    self.on_insert = on_insert
    self.on_remove = on_remove
    # Setup the media monitor,
    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(subsystem=self._subsystem, device_type=self._device_type)
    self._observer = pyudev.MonitorObserver(monitor, self._UdevEventCallback)
    self._observer.start()
    self.is_monitoring = True
    logging.info('Start monitoring media actitivities.')

  def Stop(self):
    if self.is_monitoring:
      self._observer.stop()
      self.is_monitoring = False
      logging.info('Stop monitoring media actitivities.')


class RemovableDiskMonitor(MediaMonitor):
  """MediaMonitor specifically used for monitoring removable storage devices."""
  def __init__(self):
    super(RemovableDiskMonitor, self).__init__('block', 'disk')


class MountedMedia:
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
    logging.info('Media mount directory created: %s', self._mount_dir)
    exit_code, output = subprocess.getstatusoutput(
        'mount %s %s' % (self._dev_path, self._mount_dir))
    if exit_code != 0:
      shutil.rmtree(self._mount_dir)
      raise Exception('Failed to mount. Message-%s' % output)
    self._mounted = True

  def _UmountMedia(self):
    """Umounts the partition of the media."""
    # Umount media and delete the temporary directory.
    exit_code, output = subprocess.getstatusoutput(
        'umount %s' % self._mount_dir)
    if exit_code != 0:
      raise Exception('Failed to umount. Message-%s' % output)
    shutil.rmtree(self._mount_dir)
    self._mounted = False
