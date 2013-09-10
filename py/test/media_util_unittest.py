#!/usr/bin/python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611

import commands
import glib
import gtk
import logging
import os
import pyudev
import unittest

from autotest_lib.client.common_lib.autotemp import tempfile
from cros.factory.test.media_util import MediaMonitor
from cros.factory.test.media_util import MountedMedia

# udev constants
_UDEV_ACTION_INSERT = 'add'
_UDEV_ACTION_REMOVE = 'remove'

_WRITING_TEST_FILENAME = 'media_util_unittest.test'
_WRITING_TEST_STR = 'Unittest writing test...'
_VIRTUAL_PATITION_NUMBER = 3


class TestMountedMedia(unittest.TestCase):
  def setUp(self):
    """Creates a temp file to mock as a media device."""
    self._virtual_device = tempfile(unique_id='media_util_unitttest')
    exit_code, ret = commands.getstatusoutput(
      'truncate -s 1048576 %s && mkfs -F -t ext3 %s' %
      (self._virtual_device.name, self._virtual_device.name))
    self.assertEqual(0, exit_code)

    exit_code, ret = commands.getstatusoutput('losetup --show -f %s' %
      self._virtual_device.name)
    self._free_loop_device = ret
    self.assertEqual(0, exit_code)

  def tearDown(self):
    exit_code, ret = commands.getstatusoutput(
      'losetup -d %s' % self._free_loop_device)
    self.assertEqual(0, exit_code)
    self._virtual_device.clean()

  def testFailToMount(self):
    """Tests the MountedMedia throws exceptions when it fails."""
    def with_wrapper():
      with MountedMedia('/dev/device_not_exist') as path:
        pass
    self.assertRaises(Exception, with_wrapper)

  def testNormalMount(self):
    """Tests mounting partition."""
    with MountedMedia(self._free_loop_device) as path:
      with open(os.path.join(path, _WRITING_TEST_FILENAME), 'w') as f:
        f.write(_WRITING_TEST_STR)
      with open(os.path.join(path, _WRITING_TEST_FILENAME), 'r') as f:
        self.assertEqual(_WRITING_TEST_STR, f.readline())

  def testPartitionMountSDA(self):
    """Tests mounting partition.

       This tests mounting partition with devices enumerated
       in alphabets (ex, sda).
    """
    virtual_partition = tempfile(unique_id='virtual_partition',
                                 suffix='sdc%d' %
                                 _VIRTUAL_PATITION_NUMBER)
    exit_code, ret = commands.getstatusoutput(
      'ln -s -f %s %s' %
      (self._free_loop_device, virtual_partition.name))
    self.assertEqual(0, exit_code)

    with MountedMedia(virtual_partition.name[:-1],
                      _VIRTUAL_PATITION_NUMBER) as path:
      with open(os.path.join(path, _WRITING_TEST_FILENAME), 'w') as f:
        f.write(_WRITING_TEST_STR)
      with open(os.path.join(path, _WRITING_TEST_FILENAME), 'r') as f:
        self.assertEqual(_WRITING_TEST_STR, f.readline())
    virtual_partition.clean()

  def testPartitionMountMMCBLK0(self):
    """Tests mounting partition.

       This tests mounting partition with devices enumerated
       in alphabets (ex, mmcblk0).
    """
    virtual_partition = tempfile(unique_id='virtual_partition',
                                 suffix='mmcblk0p%d' %
                                 _VIRTUAL_PATITION_NUMBER)
    exit_code, ret = commands.getstatusoutput(
      'ln -s -f %s %s' %
      (self._free_loop_device, virtual_partition.name))
    self.assertEqual(0, exit_code)

    with MountedMedia(virtual_partition.name[:-2],
                      _VIRTUAL_PATITION_NUMBER) as path:
      with open(os.path.join(path, _WRITING_TEST_FILENAME), 'w') as f:
        f.write(_WRITING_TEST_STR)
      with open(os.path.join(path, _WRITING_TEST_FILENAME), 'r') as f:
        self.assertEqual(_WRITING_TEST_STR, f.readline())
    virtual_partition.clean()

  def testPartitionMountFloppy(self):
    """Tests mounting a device without partition table."""
    with MountedMedia(self._free_loop_device, 1) as path:
      with open(os.path.join(path, _WRITING_TEST_FILENAME), 'w') as f:
        f.write(_WRITING_TEST_STR)
      with open(os.path.join(path, _WRITING_TEST_FILENAME), 'r') as f:
        self.assertEqual(_WRITING_TEST_STR, f.readline())


class TestMediaMonitor(unittest.TestCase):
  def setUp(self):
    """Creates a temp file to mock as a media device."""
    self._virtual_device = tempfile(unique_id='media_util_unitttest')
    exit_code, ret = commands.getstatusoutput(
      'truncate -s 1048576 %s' % self._virtual_device.name)
    self.assertEqual(0, exit_code)

    exit_code, ret = commands.getstatusoutput('losetup --show -f %s' %
      self._virtual_device.name)
    self._free_loop_device = ret
    self.assertEqual(0, exit_code)

  def tearDown(self):
    exit_code, ret = commands.getstatusoutput(
      'losetup -d %s' % self._free_loop_device)
    self.assertEqual(0, exit_code)
    self._virtual_device.clean()

  def testMediaMonitor(self):
    def on_insert(dev_path):
      self.assertEqual(self._free_loop_device, dev_path)
      self._media_inserted = True
      gtk.main_quit()
    def on_remove(dev_path):
      self.assertEqual(self._free_loop_device, dev_path)
      self._media_removed = True
      gtk.main_quit()
    def one_time_timer_mock_insert():
      monitor._observer.emit('device-event',
                             _UDEV_ACTION_INSERT,
                             self._mock_device)
      return False
    def one_time_timer_mock_remove():
      monitor._observer.emit('device-event',
                             _UDEV_ACTION_REMOVE,
                             self._mock_device)
      return False

    self._media_inserted = False
    self._media_removed = False
    self._context = pyudev.Context()
    self._mock_device = pyudev.Device.from_name(
      self._context, 'block',
      os.path.basename(self._free_loop_device))

    # Start the monitor.
    TIMEOUT_SECOND = 1
    monitor = MediaMonitor()
    monitor.start(on_insert=on_insert, on_remove=on_remove)
    # Simulating the insertion of a valid media device.
    timer_tag = glib.timeout_add_seconds(TIMEOUT_SECOND,
                                         one_time_timer_mock_insert)
    gtk.main()
    # Simulating the removal of a valid media device.
    glib.source_remove(timer_tag)
    timer_tag = glib.timeout_add_seconds(TIMEOUT_SECOND,
                                         one_time_timer_mock_remove)
    gtk.main()

    monitor.stop()
    self.assertEqual(True, self._media_inserted)
    self.assertEqual(True, self._media_removed)


if __name__ == '__main__':
  unittest.main()
