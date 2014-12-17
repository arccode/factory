# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""An E2E test to test the removable storage factory test."""

# pylint: disable=C0322, W0212

import mock
import os

import factory_common  # pylint: disable=W0611
from cros.factory.test.e2e_test import e2e_test
from cros.factory.test.pytests.removable_storage import removable_storage as rs
from cros.factory.utils import sync_utils
from cros.factory.utils import sys_utils


class RemovableStorageE2ETest(e2e_test.E2ETest):
  """The removable storage E2E test."""
  pytest_name = 'removable_storage'
  dargs=dict(
      block_size=512 * 1024,
      perform_random_test=False,
      perform_sequential_test=True,
      sequential_block_count=8)

  def setUp(self):
    class FakeUSBDevice(object):
      """Fake USB device object."""
      pass

    self.fake_usb_device = FakeUSBDevice()
    self.fake_usb_device.attributes = {}
    self.fake_usb_device.device_node = '/dev/fake_usb_node'
    self.fake_usb_device.device_type = ''
    self.fake_usb_device.parent = None
    self.fake_usb_device.sys_path = '/fake/sys/path'

    self.log_patcher = mock.patch.object(
        self.pytest_module, 'Log', autospec=True, return_value=True)
    self.log_patcher.start()

    self.mock_observer = mock.MagicMock()
    self.mock_observer.start = mock.Mock()

    self.pyudev_patcher = mock.patch.object(
        self.pytest_module, 'pyudev', autospec=True)
    self.mock_pyudev = self.pyudev_patcher.start()
    self.mock_pyudev.MonitorObserver = mock.Mock(
        return_value=self.mock_observer)

  def tearDown(self):
    self.log_patcher.stop()
    self.pyudev_patcher.stop()

  @e2e_test.E2ETestCase(dargs=dict(media='USB'))
  @mock.patch.object(
      rs.sys_utils, 'GetPartitions', side_effect=[
          [sys_utils.PartitionInfo(0, 0, 1000, 'fake_usb_node')], []])
  @mock.patch.object(
      rs, 'CheckOutput', side_effect=[str(4*1024*1024*1024)])
  @mock.patch.object(rs.os, 'open', side_effect=['mock_fd'])
  @mock.patch.object(rs.os, 'close')
  @mock.patch.object(rs.os, 'read')
  @mock.patch.object(rs.os, 'write')
  @mock.patch.object(rs.os, 'lseek')
  @mock.patch.object(rs.os, 'fsync')
  # pylint: disable=W0613
  def testUSB(self, mock_fsync, mock_lseek, mock_write, mock_read, mock_close,
              mock_open, mock_checkoutput, mock_get_partitions):
    mock_read.side_effect = ['\x00' * (
        self.dargs['block_size'] * self.dargs['sequential_block_count'])] * 2

    self.StartFactoryTest()

    def ObserverSetup():
      return bool(self.mock_pyudev.MonitorObserver.call_args)

    sync_utils.WaitFor(ObserverSetup, 3)
    udev_handler = self.mock_pyudev.MonitorObserver.call_args[0][1]

    # Mock insert USB.
    udev_handler(rs._UDEV_ACTION_CHANGE, self.fake_usb_device)

    # Mock remove USB.
    udev_handler(rs._UDEV_ACTION_CHANGE, self.fake_usb_device)

    self.WaitForPass()

    # Check for function calls.
    mock_fd = 'mock_fd'
    mock_checkoutput.assert_called_with(
        ['blockdev', '--getsize64', '/dev/fake_usb_node'])
    mock_open.assert_has_calls([mock.call('/dev/fake_usb_node', os.O_RDWR)])
    # os.lseek should be called five times.
    mock_lseek.assert_has_calls(
        [mock.call(mock_fd, mock.ANY, os.SEEK_SET)] * 5)
    # os.read should be called twice.
    mock_read.assert_has_calls([mock.call(mock_fd, mock.ANY)] * 2)
    # os.write should be called twice.
    mock_write.assert_has_calls([mock.call(mock_fd, mock.ANY)] * 2)
    # os.fsync should be called twice.
    mock_fsync.assert_has_calls([mock.call(mock_fd)] * 2)
    mock_close.assert_has_calls([mock.call(mock_fd)])
