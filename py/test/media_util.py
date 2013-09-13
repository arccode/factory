# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import commands
import logging
import os
import pyudev
import pyudev.glib
import shutil
import tempfile

# udev constants
_UDEV_ACTION_INSERT = 'add'
_UDEV_ACTION_REMOVE = 'remove'


class MediaMonitor(object):
  """A wrapper to monitor media events.

  This class offers an easy way to monitor the insertion and removal
  activities of media devices.

  Usage example:
    monitor = MediaMonitor()
    monitor.Start(on_insert=on_insert, on_remove=on_remove)
    monitor.Stop()
  """
  def __init__(self):
    self._monitor = None
    self._monitoring = False
    self._observer = None
    self.on_insert = None
    self.on_remove = None

  def _UdevEventCallback(self, _, action, device):
    if action == _UDEV_ACTION_INSERT:
      logging.info("Device inserted %s", device.device_node)
      self.on_insert(device.device_node)
    elif action == _UDEV_ACTION_REMOVE:
      logging.info('Device removed : %s', device.device_node)
      self.on_remove(device.device_node)

  def Start(self, on_insert, on_remove):
    if self._monitoring:
      raise Exception("Multiple start() call is not allowed")
    self.on_insert = on_insert
    self.on_remove = on_remove
    # Setup the media monitor,
    context = pyudev.Context()
    self._monitor = pyudev.Monitor.from_netlink(context)
    self._monitor.filter_by(subsystem='block', device_type='disk')
    self._observer = pyudev.glib.GUDevMonitorObserver(self._monitor)
    self._observer.connect('device-event', self._UdevEventCallback)
    self._monitoring = True
    self._monitor.start()
    logging.info("Monitoring media actitivity")

  def Stop(self):
    # TODO(itspeter) : Add stop functionality as soon as
    #                  pyudev.Monitor support it.
    self._monitoring = False

  # TODO(littlecvr): Remove this wrapper as soon as CL:169470 "Change
  #                  callers to match media_util's new API" got merged.
  def start(self, on_insert, on_remove):
    self.Start(on_insert, on_remove)

  # TODO(littlecvr): Remove this wrapper as soon as CL:169470 "Change
  #                  callers to match media_util's new API" got merged.
  def stop(self):
    self.Stop()


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
