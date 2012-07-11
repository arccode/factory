# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


# DESCRIPTION :
#
# This is a factory test to test removable storage devices.
# We implement the following tests:
#   * Random and sequential read / write test
#   * Lock (write protection) test

import os
import pyudev
import random
import subprocess
import threading
import time
import unittest

from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates


_STATE_RW_TEST_WAIT_INSERT = 1
_STATE_RW_TEST_WAIT_REMOVE = 2
_STATE_LOCKTEST_WAIT_INSERT = 3
_STATE_LOCKTEST_WAIT_REMOVE = 4

# udev constants
_UDEV_ACTION_INSERT = 'add'
_UDEV_ACTION_REMOVE = 'remove'
_UDEV_MMCBLK_PATH   = '/dev/mmcblk'
# USB card reader attributes and common text string in descriptors
_USB_CARD_ATTRS   = ['vendor', 'model', 'product', 'configuration',
                     'manufacturer']
_USB_CARD_DESCS   = ['card', 'reader']

# The GPT ( http://en.wikipedia.org/wiki/GUID_Partition_Table )
# occupies the first 34 and the last 33 512-byte blocks.
#
# We don't want to upset kernel by changing the partition table.
# Skip the first 34 and the last 33 512-byte blocks when doing
# read/write tests.
_SECTOR_SIZE = 512
_SKIP_HEAD_BLOCK = 34
_SKIP_TAIL_BLOCK = 33

# Read/Write test modes
_RW_TEST_MODE_RANDOM = 1
_RW_TEST_MODE_SEQUENTIAL = 2

_RW_TEST_INSERT_FMT_STR = (
    lambda t: test_ui.MakeLabel(
      '<br/>'.join(['insert %s drive for read/write test...' % t,
                    'WARNING: DATA ON INSERTED MEDIA WILL BE LOST!']),
      '<br/>'.join([u'插入%s存儲以進行讀寫測試...' % t,
                    u'注意: 插入裝置上的資料將會被清除!'])))
_REMOVE_FMT_STR = lambda t: test_ui.MakeLabel('remove %s drive...' % t,
                                              u'提取%s存儲...' % t)
_TESTING_FMT_STR = lambda t: test_ui.MakeLabel('testing %s...' % t,
                                               u'%s 檢查中...' % t)
_LOCKTEST_INSERT_FMT_STR = (
    lambda t:
      test_ui.MakeLabel('toggle lock switch and insert %s drive again...' % t,
                        u'切換防寫開關並再次插入%s存儲...' % t))
_LOCKTEST_REMOVE_FMT_STR = (
    lambda t:
      test_ui.MakeLabel('remove %s drive and toggle lock switch...' % t,
                        u'提取%s存儲並關閉防寫開關...' % t))
_ERR_REMOVE_TOO_EARLY_FMT_STR = (
    lambda t:
      test_ui.MakeLabel('Device removed too early (%s).' % t,
                        u'太早移除外部儲存裝置 (%s).' % t))
_ERR_TEST_FAILED_FMT_STR = (
    lambda test_name, target_dev:
      'IO error while running %s test on %s.' % (test_name, target_dev))
_ERR_GET_DEV_SIZE_FAILED_FMT_STR = (
    lambda target_dev: 'Unable to determine dev size of %s.' % target_dev)
_ERR_RO_TEST_FAILED_FMT_STR = (
    lambda target_dev: 'Unable to get RO status of %s.' % target_dev)
_ERR_LOCKTEST_FAILED_FMT_STR = (
    lambda target_dev: 'Locktest failed on %s.' % target_dev)
_ERR_DEVICE_READ_ONLY_STR = (
    lambda target_dev: '%s is read-only.' % target_dev)
_TEST_TITLE = test_ui.MakeLabel('Card Reader Test', u'讀卡機測試')
_IMG_HTML_TAG = (
    lambda src: '<img src="%s" style="display:block; margin:0 auto;"/>' % src)


class PyudevThread(threading.Thread):
  '''A thread class for monitoring udev events in the background.'''

  def __init__(self, callback, **udev_filters):
    threading.Thread.__init__(self)
    self._callback = callback
    self._udev_filters = dict(udev_filters)

  def run(self):
    '''Create a loop to monitor udev events and invoke callback function.'''
    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(**self._udev_filters)
    for action, device in monitor:
      self._callback(action, device)


class RemovableStorageTest(unittest.TestCase):

  def __init__(self, *args, **kwargs):
    super(RemovableStorageTest, self).__init__(*args, **kwargs)
    self._media = None
    self._vidpid = None
    self._block_size = 1024
    self._random_block_count = 3
    self._perform_sequential_test = False
    self._sequential_block_count = 1024
    self._ui = test_ui.UI()
    self._template = ui_templates.TwoSections(self._ui)
    self._perform_locktest = False
    self._error = ''
    self._target_device = None
    self._insertion_image = None
    self._removal_image = None
    self._testing_image = None
    self._locktest_insertion_image = None
    self._locktest_removal_image = None
    self._state = None
    self._pyudev_thread = None
    self._total_tests = 0
    self._finished_tests = 0

  def GetAttrs(self, device, key_set):
    if device is None:
      return ''
    attrs = [device.attributes[key] for key in
             set(device.attributes.keys()) & key_set]
    attr_str = ' '.join(attrs).strip()
    if len(attr_str):
      attr_str = '/' + attr_str
    return self.GetAttrs(device.parent, key_set) + attr_str

  def GetVidpid(self, device):
    if device is None:
      return None
    if device.device_type == 'usb_device':
      attrs = device.attributes
      if set(['idProduct', 'idVendor']) <= set(attrs.keys()):
        vidpid = attrs['idVendor'] + ':' + attrs['idProduct']
        return vidpid.strip()
    return self.GetVidpid(device.parent)

  def IsUSBCardReader(self, device):
    attr_str = self.GetAttrs(device, set(_USB_CARD_ATTRS)).lower()
    for desc in _USB_CARD_DESCS:
      if desc in attr_str:
        return True
    return False

  def IsSD(self, device):
    if device.device_node.find(_UDEV_MMCBLK_PATH) == 0:
      return True
    return self.IsUSBCardReader(device)

  def GetDeviceType(self, device):
    if self.IsSD(device):
      return 'SD'
    return 'USB'

  def GetDeviceSize(self, dev_path):
    '''Get device size in bytes.

    Args:
      dev_path: path to device file.
    '''
    subp = subprocess.Popen(['blockdev', '--getsize64', dev_path],
                            stdout=subprocess.PIPE)
    dev_size = subp.communicate()[0]

    if subp.returncode != 0 or dev_size is None:
      self._ui.Fail(_ERR_GET_DEV_SIZE_FAILED_FMT_STR(dev_path))

    dev_size = int(dev_size)
    gb = dev_size / 1000.0 / 1000.0 / 1000.0
    factory.console.info('dev size of %s : %d bytes (%.3f GB)' %
                         (dev_path, dev_size, gb))

    return dev_size

  def GetDeviceRo(self, dev_path):
    '''Get device read-only flag.

    Args:
      dev_path: path to device file.
    '''
    subp = subprocess.Popen(['blockdev', '--getro', dev_path],
                            stdout=subprocess.PIPE)
    ro = subp.communicate()[0]

    if subp.returncode != 0 or ro is None:
      self._ui.Fail(_ERR_RO_TEST_FAILED_FMT_STR(dev_path))

    ro = int(ro)
    factory.console.info('%s RO : %d' % (dev_path, ro))

    return ro == 1

  def TestReadWrite(self):
    '''Random and sequential read / write tests.

    This method executes only random read / write test by default.
    Sequential read / write test can be enabled through dargs.
    '''
    self._template.SetInstruction(_TESTING_FMT_STR(self._target_device))
    self._template.SetState(_IMG_HTML_TAG(self._testing_image))

    dev_path = self._target_device
    dev_size = self.GetDeviceSize(dev_path)
    dev_fd = None
    ok = True
    total_time_read = 0.0
    total_time_write = 0.0

    mode = [_RW_TEST_MODE_RANDOM]
    if self._perform_sequential_test is True:
      mode.append(_RW_TEST_MODE_SEQUENTIAL)
    for m in mode:
      if m == _RW_TEST_MODE_RANDOM:
        # Read/Write one block each time
        bytes_to_operate = self._block_size
        loop = self._random_block_count
        factory.console.info('Performing r/w test on %d %d-byte random blocks' %
                             (loop, self._block_size))
      elif m == _RW_TEST_MODE_SEQUENTIAL:
        # Converts block counts into bytes
        bytes_to_operate = (self._sequential_block_count *
                            self._block_size)
        loop = 1
        factory.console.info('Performing sequential r/w test of %d bytes' %
                             bytes_to_operate)

      try:
        dev_fd = os.open(dev_path, os.O_RDWR)
      except Exception as e:  # pylint: disable=W0703
        ok = False
        factory.console.error('Unable to open %s : %s' % (dev_path, e))

      if dev_fd is not None:
        blocks = dev_size / _SECTOR_SIZE
        # Determine the range in which the random block is selected
        random_head = _SKIP_HEAD_BLOCK
        random_tail = (blocks - _SKIP_TAIL_BLOCK -
                       int(bytes_to_operate / _SECTOR_SIZE))

        if dev_size > 0x7FFFFFFF:
          # The following try...except section is for system that does
          # not have large file support enabled for Python. This is
          # typically observed on 32-bit machines. In some 32-bit
          # machines, doing seek() with an offset larger than 0x7FFFFFFF
          # (which is the largest possible value of singned int) will
          # cause OverflowError, due to failed conversion from long int
          # to int.
          try:
            # Test whether large file support is enabled or not.
            os.lseek(dev_fd, 0x7FFFFFFF + 1, os.SEEK_SET)
          except OverflowError:
            # The system does not have large file support, so we
            # restrict the range in which we perform the random r/w
            # test.
            random_tail = min(
                random_tail,
                int(0x7FFFFFFF / _SECTOR_SIZE) -
                int(bytes_to_operate / _SECTOR_SIZE))
            factory.console.info('No large file support')

        if random_tail < random_head:
          self._ui.Fail('Block size too large for r/w test.')

        random.seed()
        for x in range(loop): # pylint: disable=W0612
          # Select one random block as starting point.
          random_block = random.randint(random_head, random_tail)
          offset = random_block * _SECTOR_SIZE

          try:
            os.lseek(dev_fd, offset, os.SEEK_SET)
            read_start = time.time()
            in_block = os.read(dev_fd, bytes_to_operate)
            read_finish = time.time()
          except Exception as e:  # pylint: disable=W0703
            factory.console.error('Failed to read block %s' % e)
            ok = False
            break

          if m == _RW_TEST_MODE_RANDOM:
            # Modify the first byte and write the whole block back.
            out_block = chr(ord(in_block[0]) ^ 0xff) + in_block[1:]
          elif m == _RW_TEST_MODE_SEQUENTIAL:
            out_block = chr(0x00) * bytes_to_operate
          try:
            os.lseek(dev_fd, offset, os.SEEK_SET)
            write_start = time.time()
            os.write(dev_fd, out_block)
            os.fsync(dev_fd)
            write_finish = time.time()
          except Exception as e:  # pylint: disable=W0703
            factory.console.error('Failed to write block %s' % e)
            ok = False
            break

          # Check if the block was actually written, and restore the
          # original content of the block.
          os.lseek(dev_fd, offset, os.SEEK_SET)
          b = os.read(dev_fd, bytes_to_operate)
          if b != out_block:
            factory.console.error('Failed to write block')
            ok = False
            break
          os.lseek(dev_fd, offset, os.SEEK_SET)
          os.write(dev_fd, in_block)
          os.fsync(dev_fd)

          total_time_read += read_finish - read_start
          total_time_write += write_finish - write_start

        # Make sure we close() the device file so later tests won't
        # fail.
        os.close(dev_fd)

      self.AdvanceProgress()
      if ok is False:
        if self.GetDeviceRo(dev_path) is True:
          factory.console.warn('Is write protection on?')
          self._ui.FailLater(_ERR_DEVICE_READ_ONLY_STR(dev_path))
        test_name = ''
        if m == _RW_TEST_MODE_RANDOM:
          test_name = 'random r/w'
        elif m == _RW_TEST_MODE_SEQUENTIAL:
          test_name = 'sequential r/w'
        self._ui.FailLater(_ERR_TEST_FAILED_FMT_STR(test_name,
                                                    self._target_device))
      else:
        if m == _RW_TEST_MODE_RANDOM:
          factory.console.info(
              'random_read_speed: %.3f MB/s' %
              ((self._block_size * loop) / total_time_read / 1000 / 1000))
          factory.console.info(
              'random_write_speed: %.3f MB/s' %
              ((self._block_size * loop) / total_time_write / 1000 / 1000))
        elif m == _RW_TEST_MODE_SEQUENTIAL:
          factory.console.info(
              'sequential_read_speed: %.3f MB/s' %
              (bytes_to_operate / total_time_read / 1000 / 1000))
          factory.console.info(
              'sequential_write_speed: %.3f MB/s' %
              (bytes_to_operate / total_time_write / 1000 / 1000))

    self._template.SetInstruction(_REMOVE_FMT_STR(self._media))
    self._state = _STATE_RW_TEST_WAIT_REMOVE
    self._template.SetState(_IMG_HTML_TAG(self._removal_image))

  def TestLock(self):
    '''SD card write protection test.'''
    self._template.SetInstruction(_TESTING_FMT_STR(self._target_device))
    self._template.SetState(_IMG_HTML_TAG(self._testing_image))

    ro = self.GetDeviceRo(self._target_device)

    if ro is False:
      self._ui.FailLater(_ERR_LOCKTEST_FAILED_FMT_STR(self._target_device))
    self._template.SetInstruction(_LOCKTEST_REMOVE_FMT_STR(self._media))
    self._state = _STATE_LOCKTEST_WAIT_REMOVE
    self._template.SetState(_IMG_HTML_TAG(self._locktest_removal_image))
    self.AdvanceProgress()

  def UdevEventCallback(self, action, device):
    if action == _UDEV_ACTION_INSERT:
      if self._state == _STATE_RW_TEST_WAIT_INSERT:
        if self._vidpid is None:
          if self._media != self.GetDeviceType(device):
            return True
        else:
          device_vidpid = self.GetVidpid(device)
          if device_vidpid not in self._vidpid:
            return True
          factory.console.info('VID:PID == %s' % self._vidpid)
        factory.console.info('%s device inserted : %s' %
                             (self._media, device.device_node))
        self._target_device = device.device_node
        self.TestReadWrite()
      elif self._state == _STATE_LOCKTEST_WAIT_INSERT:
        factory.console.info('%s device inserted : %s' %
                             (self._media, device.device_node))
        if self._target_device == device.device_node:
          self.TestLock()
    elif action == _UDEV_ACTION_REMOVE:
      if self._target_device == device.device_node:
        factory.console.info('Device removed : %s' % device.device_node)
        if self._state == _STATE_RW_TEST_WAIT_REMOVE:
          if self._perform_locktest:
            self._template.SetInstruction(
                _LOCKTEST_INSERT_FMT_STR(self._media))
            self._state = _STATE_LOCKTEST_WAIT_INSERT
            self._template.SetState(
                _IMG_HTML_TAG(self._locktest_insertion_image))
          else:
            self._ui.Pass()
        elif self._state == _STATE_LOCKTEST_WAIT_REMOVE:
          self._ui.Pass()
        else:
          self._template.SetInstruction(
              _ERR_REMOVE_TOO_EARLY_FMT_STR(self._target_device))
          self._ui.Fail('Device %s removed too early' % self._target_device)
    return True

  def AdvanceProgress(self, value=1):
    self._finished_tests += value
    if self._finished_tests > self._total_tests:
      self._finished_tests = self._total_tests
    self._template.SetProgressBarValue(
        100 * self._finished_tests / self._total_tests)

  def runTest(self):
    '''Main entrance of removable storage test.

    Test parameters:
      media:
        Media type [None]
      vipid:
        Vender ID and Product ID of the target testing device [None]
      block_size:
        Size of each block in bytes used in read / write test [1024]
      random_block_count:
        Number of blocks to test during random read / write test [3]
      perform_sequential:
        Whether to run sequential read / write test [False]
      sequential_block_count:
        Number of blocks to test in sequential read / write test [1024]
      perform_locktest:
        Whether to run lock test [False]
    '''
    args = self.test_info.args  # pylint: disable=E1101
    self._media = args.get('media')
    self._vidpid = args.get('vidpid')
    self._block_size = args.get('block_size', 1024)
    self._random_block_count = args.get('random_block_count', 3)
    self._perform_sequential_test = args.get('perform_sequential_test', False)
    self._sequential_block_count = args.get('sequential_block_count', 1024)
    self._perform_locktest = args.get('perform_locktest', False)

    os.chdir(os.path.join(os.path.dirname(__file__), '%s_static' %
                          self.test_info.pytest_name)) # pylint: disable=E1101

    if self._vidpid and type(self._vidpid) != type(list()):
      # Convert vidpid to a list.
      self._vidpid = [self._vidpid]

    factory.console.info('media = %s' % self._media)

    self._template.SetTitle(_TEST_TITLE)
    self._insertion_image = '%s_insert.png' % self._media
    self._removal_image = '%s_remove.png' % self._media
    self._testing_image = '%s_testing.png' % self._media

    if self._perform_locktest:
      self._locktest_insertion_image = '%s_locktest_insert.png' % self._media
      self._locktest_removal_image = '%s_locktest_remove.png' % self._media

    self._template.SetInstruction(_RW_TEST_INSERT_FMT_STR(self._media))
    self._state = _STATE_RW_TEST_WAIT_INSERT
    self._template.SetState(_IMG_HTML_TAG(self._insertion_image))

    # Initialize progress bar
    self._template.DrawProgressBar()
    self._total_tests = 1
    if self._perform_sequential_test:
      self._total_tests += 1
    if self._perform_locktest:
      self._total_tests += 1
    self._finished_tests = 0
    self._template.SetProgressBarValue(0)

    # Create a daemon pyudev thread to listen to device events
    self._pyudev_thread = PyudevThread(self.UdevEventCallback,
                                       subsystem='block',
                                       device_type='disk')
    self._pyudev_thread.daemon = True
    self._pyudev_thread.start()

    self._ui.Run()
