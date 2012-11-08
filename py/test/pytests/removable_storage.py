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
import logging
import pyudev
import random
import threading
import time
import unittest

from cros.factory.event_log import EventLog
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test import utils
from cros.factory.test.args import Arg


_STATE_RW_TEST_WAIT_INSERT = 1
_STATE_RW_TEST_WAIT_REMOVE = 2
_STATE_LOCKTEST_WAIT_INSERT = 3
_STATE_LOCKTEST_WAIT_REMOVE = 4

# udev constants
_UDEV_ACTION_INSERT = 'add'
_UDEV_ACTION_REMOVE = 'remove'
_UDEV_ACTION_CHANGE = 'change'
_UDEV_MMCBLK_PATH   = '/dev/mmcblk'
# USB card reader attributes and common text string in descriptors
_CARD_READER_ATTRS = ['vendor', 'model', 'product', 'configuration',
                      'manufacturer', 'driver']
_CARD_READER_DESCS = ['sd', 'card', 'reader']

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

_MILLION = 1000000

_RW_TEST_INSERT_FMT_STR = (
    lambda t: test_ui.MakeLabel(
      '<br/>'.join(['Insert %s drive for read/write test...' % t,
                    'WARNING: DATA ON INSERTED MEDIA WILL BE LOST!']),
      '<br/>'.join([u'插入 %s 存储以进行读写测试...' % t,
                    u'注意: 插入装置上的资料将会被清除!'])))
_REMOVE_FMT_STR = lambda t: test_ui.MakeLabel('Remove %s drive...' % t,
                                              u'提取 %s 存储...' % t)
_TESTING_FMT_STR = lambda t: test_ui.MakeLabel('Testing %s...' % t,
                                               u'%s 检查中...' % t)
_TESTING_RANDOM_RW_FMT_STR = lambda loop, bsize: test_ui.MakeLabel(
    'Performing r/w test on %d %d-byte random blocks...</br>' % (loop, bsize),
    u'执行 %d 个 %d 字节区块随机读写测试...</br>' % (loop, bsize))
_TESTING_SEQUENTIAL_RW_FMT_STR = lambda bsize: test_ui.MakeLabel(
    'Performing sequential r/w test of %d bytes...</br>' % bsize,
    u'执行 %d 字节区块连续读写测试...</br>' % bsize)
_LOCKTEST_INSERT_FMT_STR = (
    lambda t:
      test_ui.MakeLabel('Toggle lock switch and insert %s drive again...' % t,
                        u'切换写保护开关并再次插入 %s 存储...' % t))
_LOCKTEST_REMOVE_FMT_STR = (
    lambda t:
      test_ui.MakeLabel('Remove %s drive and toggle lock switch...' % t,
                        u'提取 %s 存储并关闭写保护开关...' % t))
_ERR_REMOVE_TOO_EARLY_FMT_STR = (
    lambda t:
      test_ui.MakeLabel('Device removed too early (%s).' % t,
                        u'太早移除外部储存装置 (%s).' % t))
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
_ERR_SPEED_CHECK_FAILED_FMT_STR = (
    lambda test_type, target_dev:
        '%s_speed of %s does not meet lower bound.' % (test_type, target_dev))
_TEST_TITLE = test_ui.MakeLabel('Card Reader Test', u'读卡机测试')
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
  # pylint: disable=E1101

  def __init__(self, *args, **kwargs):
    super(RemovableStorageTest, self).__init__(*args, **kwargs)
    self._ui = test_ui.UI()
    self._template = ui_templates.TwoSections(self._ui)
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
    self._metrics = {}

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

  def IsSD(self, device):
    if device.device_node.find(_UDEV_MMCBLK_PATH) == 0:
      return True
    attr_str = self.GetAttrs(device, set(_CARD_READER_ATTRS)).lower()
    for desc in _CARD_READER_DESCS:
      if desc in attr_str:
        return True
    return False

  def GetDeviceType(self, device):
    if self.IsSD(device):
      return 'SD'
    return 'USB'

  def GetDeviceSize(self, dev_path):
    '''Get device size in bytes.

    Args:
      dev_path: path to device file.
    '''
    try:
      dev_size = utils.CheckOutput(['blockdev', '--getsize64', dev_path])
    except:  # pylint: disable=W0702
      self._ui.Fail(_ERR_GET_DEV_SIZE_FAILED_FMT_STR(dev_path))

    if not dev_size:
      self._ui.Fail(_ERR_GET_DEV_SIZE_FAILED_FMT_STR(dev_path))

    dev_size = int(dev_size)
    gb = dev_size / 1000000000.0
    logging.info('Dev size of %s : %d bytes (%.3f GB)', dev_path, dev_size, gb)

    return dev_size

  def GetDeviceRo(self, dev_path):
    '''Get device read-only flag.

    Args:
      dev_path: path to device file.
    '''
    try:
      ro = utils.CheckOutput(['blockdev', '--getro', dev_path])
    except:  # pylint: disable=W0702
      self._ui.Fail(_ERR_RO_TEST_FAILED_FMT_STR(dev_path))

    ro = int(ro)
    logging.info('%s RO : %d', dev_path, ro)

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

    mode = []
    if self.args.perform_random_test is True:
      mode.append(_RW_TEST_MODE_RANDOM)
    if self.args.perform_sequential_test is True:
      mode.append(_RW_TEST_MODE_SEQUENTIAL)
    for m in mode:
      if m == _RW_TEST_MODE_RANDOM:
        # Read/Write one block each time
        bytes_to_operate = self.args.block_size
        loop = self.args.random_block_count
        self._template.SetState(
            _TESTING_RANDOM_RW_FMT_STR(loop, bytes_to_operate), append=True)
      elif m == _RW_TEST_MODE_SEQUENTIAL:
        # Converts block counts into bytes
        bytes_to_operate = (self.args.sequential_block_count *
                            self.args.block_size)
        loop = 1
        self._template.SetState(
            _TESTING_SEQUENTIAL_RW_FMT_STR(bytes_to_operate), append=True)

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
            logging.info('No large file support')

        if random_tail < random_head:
          self._ui.Fail('Block size too large for r/w test.')

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
        update_bin = {}
        def _CheckThreshold(test_type, value, threshold):
          update_bin['%s_speed' % test_type] = value
          logging.info('%s_speed: %.3f MB/s', test_type, value)
          if threshold:
            update_bin['%s_threshold' % test_type] = threshold
            if value < threshold:
              self._ui.FailLater(_ERR_SPEED_CHECK_FAILED_FMT_STR(
                  test_type, self._target_device))

        if m == _RW_TEST_MODE_RANDOM:
          random_read_speed = (
              (self.args.block_size * loop) / total_time_read / _MILLION)
          random_write_speed = (
              (self.args.block_size * loop) / total_time_write / _MILLION)
          _CheckThreshold('random_read', random_read_speed,
                          self.args.random_read_threshold)
          _CheckThreshold('random_write', random_write_speed,
                          self.args.random_write_threshold)
        elif m == _RW_TEST_MODE_SEQUENTIAL:
          sequential_read_speed = (
              bytes_to_operate / total_time_read / _MILLION)
          sequential_write_speed = (
              bytes_to_operate / total_time_write / _MILLION)
          _CheckThreshold('sequential_read', sequential_read_speed,
                          self.args.sequential_read_threshold)
          _CheckThreshold('sequential_write', sequential_write_speed,
                          self.args.sequential_write_threshold)

        self._metrics.update(update_bin)

    EventLog.ForAutoTest().Log(('%s_rw_speed' % self.args.media),
                               **self._metrics)
    self._template.SetInstruction(_REMOVE_FMT_STR(self.args.media))
    self._state = _STATE_RW_TEST_WAIT_REMOVE
    self._template.SetState(_IMG_HTML_TAG(self._removal_image))

  def TestLock(self):
    '''SD card write protection test.'''
    self._template.SetInstruction(_TESTING_FMT_STR(self._target_device))
    self._template.SetState(_IMG_HTML_TAG(self._testing_image))

    ro = self.GetDeviceRo(self._target_device)

    if ro is False:
      self._ui.FailLater(_ERR_LOCKTEST_FAILED_FMT_STR(self._target_device))
    self._template.SetInstruction(_LOCKTEST_REMOVE_FMT_STR(self.args.media))
    self._state = _STATE_LOCKTEST_WAIT_REMOVE
    self._template.SetState(_IMG_HTML_TAG(self._locktest_removal_image))
    self.AdvanceProgress()

  def UdevEventCallback(self, action, device):
    if action == _UDEV_ACTION_CHANGE:
      node = os.path.basename(device.device_node)
      if any(len(x) > 3 and x[3] == node for x in
             [l.strip().split() for l in open('/proc/partitions').readlines()]):
        action = _UDEV_ACTION_INSERT
      else:
        action = _UDEV_ACTION_REMOVE

    if action == _UDEV_ACTION_INSERT:
      if self._state == _STATE_RW_TEST_WAIT_INSERT:
        if self.args.vidpid:
          device_vidpid = self.GetVidpid(device)
          if device_vidpid not in self.args.vidpid:
            return True
          logging.info('VID:PID == %s', self.args.vidpid)
        elif self.args.sysfs_path:
          if (not os.path.exists(self.args.sysfs_path) or
              not self.args.sysfs_path in device.sys_path):
            return True
          logging.info('sys path = %s', self.args.sysfs_path)
        else:
          if self.args.media != self.GetDeviceType(device):
            return True
        logging.info('%s device inserted : %s', (self.args.media,
                                                 device.device_node))
        self._target_device = device.device_node
        self.TestReadWrite()
      elif self._state == _STATE_LOCKTEST_WAIT_INSERT:
        logging.info('%s device inserted : %s', (self.args.media,
                                                 device.device_node))
        if self._target_device == device.device_node:
          self.TestLock()
    elif action == _UDEV_ACTION_REMOVE:
      if self._target_device == device.device_node:
        logging.info('Device removed : %s', device.device_node)
        if self._state == _STATE_RW_TEST_WAIT_REMOVE:
          if self.args.perform_locktest:
            self._template.SetInstruction(
                _LOCKTEST_INSERT_FMT_STR(self.args.media))
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

  ARGS = [
    Arg('media', str, 'Media type'),
    Arg('vidpid', (str, list),
        'Vendor ID and Product ID of the target testing device', None,
        optional=True),
    Arg('sysfs_path', str, 'The expected sysfs path that udev events should'
        'come from, ex: /sys/devices/pci0000:00/0000:00:1a.0/usb1/1-1/1-1.2',
        None, optional=True),
    Arg('block_size', int,
        'Size of each block in bytes used in read / write test', 1024),
    Arg('perform_random_test', bool,
        'Whether to run random read / write test', True),
    Arg('random_read_threshold', (int, float),
        'The lowest random read rate the device should achieve', None,
        optional=True),
    Arg('random_write_threshold', (int, float),
        'The lowest random write rate the device should achieve', None,
        optional=True),
    Arg('random_block_count', int,
        'Number of blocks to test during random read / write test', 3),
    Arg('perform_sequential_test', bool,
        'Whether to run sequential read / write tes', False),
    Arg('sequential_read_threshold', (int, float),
        'The lowest sequential read rate the device should achieve',
        None, optional=True),
    Arg('sequential_write_threshold', (int, float),
        'The lowest sequential write rate the device should achieve',
        None, optional=True),
    Arg('sequential_block_count', int,
        'Number of blocks to test in sequential read / write test', 1024),
    Arg('perform_locktest', bool, 'Whether to run lock test', False)
  ]

  def runTest(self):
    '''Main entrance of removable storage test.'''
    os.chdir(os.path.join(os.path.dirname(__file__), '%s_static' %
                          self.test_info.pytest_name)) # pylint: disable=E1101

    random.seed(0)

    if self.args.vidpid and type(self.args.vidpid) != type(list()):
      # Convert vidpid to a list.
      self.args.vidpid = [self.args.vidpid]

    logging.info('media = %s', self.args.media)

    self._template.SetTitle(_TEST_TITLE)
    self._insertion_image = '%s_insert.png' % self.args.media
    self._removal_image = '%s_remove.png' % self.args.media
    self._testing_image = '%s_testing.png' % self.args.media

    if self.args.perform_locktest:
      self._locktest_insertion_image = ('%s_locktest_insert.png' %
                                        self.args.media)
      self._locktest_removal_image = '%s_locktest_remove.png' % self.args.media

    self._template.SetInstruction(_RW_TEST_INSERT_FMT_STR(self.args.media))
    self._state = _STATE_RW_TEST_WAIT_INSERT
    self._template.SetState(_IMG_HTML_TAG(self._insertion_image))

    # Initialize progress bar
    self._template.DrawProgressBar()
    self._total_tests = 0
    if self.args.perform_random_test:
      self._total_tests += 1
    if self.args.perform_sequential_test:
      self._total_tests += 1
    if self.args.perform_locktest:
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
