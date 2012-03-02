# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import commands
import logging
import os
import pyudev
import pyudev.glib

from autotest_lib.client.common_lib.autotemp import tempdir

# udev constants
_UDEV_ACTION_INSERT = 'add'
_UDEV_ACTION_REMOVE = 'remove'


class MediaMonitor():
    """A wrapper to monitor media events.

    This class offers an easy way to monitor the insertion and removal
    activities of media devices.

    Usage example:
        monitor = MediaMonitor()
        monitor.start(on_insert=on_insert, on_remove=on_remove)
        monitor.stop()
    """
    def __init__(self):
        self._monitoring = False

    def udev_event_callback(self, _, action, device):
        if action == _UDEV_ACTION_INSERT:
            logging.info("Device inserted %s" % device.device_node)
            self.on_insert(device.device_node)
        elif action == _UDEV_ACTION_REMOVE:
            logging.info('Device removed : %s' % device.device_node)
            self.on_remove(device.device_node)

    def start(self, on_insert, on_remove):
        if self._monitoring:
            raise Exception("Multiple start() call is not allowed")
        self.on_insert = on_insert
        self.on_remove = on_remove
        # Setup the media monitor,
        context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(context)
        self.monitor.filter_by(subsystem='block', device_type='disk')
        observer = pyudev.glib.GUDevMonitorObserver(self.monitor)
        observer.connect('device-event', self.udev_event_callback)
        self._monitoring = True
        self._observer = observer
        self.monitor.start()
        logging.info("Monitoring media actitivity")

    def stop(self):
        # TODO(itspeter) : Add stop functionality as soon as
        #                  pyudev.Monitor support it.
        self._monitoring = False


class MountedMedia():
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
        self._mount_media()
        return self.mount_dir.name

    def __exit__(self, type, value, traceback):
        if self._mounted:
            self._umount_media()
        return True

    def _mount_media(self):
        """Mount a partition of media at temporary directory.

        Exceptions are throwed if anything goes wrong.
        """
        # Create an temporary mount directory to mount.
        self.mount_dir = tempdir(unique_id='MountedMedia')
        logging.info("Media mount directory created: %s" % self.mount_dir.name)
        exit_code, output = commands.getstatusoutput(
                'mount %s %s' % (self._dev_path, self.mount_dir.name))
        if exit_code != 0:
            self.mount_dir.clean()
            raise Exception("Failed to mount. Message-%s" % output)
        self._mounted = True

    def _umount_media(self):
        """Umounts the partition of the media."""
        # Umount media and delete the temporary directory.
        exit_code, output = commands.getstatusoutput(
                'umount %s' % self.mount_dir.name)
        if exit_code != 0:
            raise Exception("Failed to umount. Message-%s" % output)
        self.mount_dir.clean()
        self._mounted = False
