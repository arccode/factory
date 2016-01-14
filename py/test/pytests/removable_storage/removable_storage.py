# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests removable storage devices.

The following test functions are supported:

- Random and sequential read / write test
- Lock (write protection) test
"""

from __future__ import print_function

import logging
import random
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import countdown_timer
from cros.factory.test import dut
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.event_log import Log
from cros.factory.test.fixture.bft_fixture import (BFTFixtureException,
                                                   CreateBFTFixture,
                                                   TEST_ARG_HELP)
from cros.factory.utils import time_utils

_STATE_RW_TEST_WAIT_INSERT = 1
_STATE_RW_TEST_WAIT_REMOVE = 2
_STATE_LOCKTEST_WAIT_INSERT = 3
_STATE_LOCKTEST_WAIT_REMOVE = 4
_STATE_ACCESSING = 5

# The GPT ( http://en.wikipedia.org/wiki/GUID_Partition_Table )
# occupies the first 34 and the last 33 512-byte blocks.
#
# We don't want to upset kernel by changing the partition table.
# Skip the first 34 and the last 33 512-byte blocks when doing
# read/write tests.
_SECTOR_SIZE = 512
_SKIP_HEAD_SECTOR = 34
_SKIP_TAIL_SECTOR = 33

# Read/Write test modes
_RW_TEST_MODE_RANDOM = 1
_RW_TEST_MODE_SEQUENTIAL = 2

# Mininum size required for partition test
_MIN_PARTITION_SIZE_MB = 1

_MILLION = 1000000

_RW_TEST_INSERT_FMT_STR = (
    lambda t, extra_en, extra_zh: test_ui.MakeLabel(
        '<br/>'.join(['Insert %s drive for read/write test... %s' % (t, extra_en),
                      'WARNING: DATA ON INSERTED MEDIA WILL BE LOST!']),
        '<br/>'.join([u'插入 %s 存储以进行读写测试... %s' % (t, extra_zh),
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
_ERR_CREATE_PARTITION_FMT_STR = (
    lambda test_type, target_dev, dev_size:
    'The size on %s device %s is too small (only %d bytes) for '
    'partition test.' % (test_type, target_dev, dev_size))
_ERR_VERIFY_PARTITION_FMT_STR = (
    lambda test_type, target_dev:
    'Partition verification failed on %s device %s. Problem with card '
    'reader module maybe?' % (test_type, target_dev))
_ERR_BFT_ACTION_STR = (
    lambda action, test_type, target_dev, reason:
    'BFT fixture failed to %s %s device %s. Reason: %s' % (
        action, test_type, target_dev, reason))

_TEST_TITLE = test_ui.MakeLabel('Removable Storage Test', u'可移除储存装置测试')

_ID_STATE_DIV = 'state_div'
_ID_COUNTDOWN_DIV = 'countdown_div'
_TEST_HTML = '<div id="%s"></div><div id="%s"></div>' % (
    _ID_STATE_DIV, _ID_COUNTDOWN_DIV)
_IMG_HTML_TAG = (
    lambda src: '<img src="%s" style="display:block; margin:0 auto;"/>' % src)


class RemovableStorageTest(unittest.TestCase):
  """The removable storage factory test."""
  ARGS = [
      Arg('media', str, 'Media type'),
      Arg(
          'sysfs_path', str,
          'The expected sysfs path that udev events should '
          'come from, ex: /sys/devices/pci0000:00/0000:00:1a.0/usb1/1-1/1-1.2',
          None),
      Arg(
          'block_size', int,
          'Size of each block in bytes used in read / write test', 1024),
      Arg(
          'perform_random_test', bool,
          'Whether to run random read / write test', True),
      Arg(
          'random_read_threshold', (int, float),
          'The lowest random read rate the device should achieve', None,
          optional=True),
      Arg(
          'random_write_threshold', (int, float),
          'The lowest random write rate the device should achieve', None,
          optional=True),
      Arg(
          'random_block_count', int,
          'Number of blocks to test during random read / write test', 3),
      Arg(
          'perform_sequential_test', bool,
          'Whether to run sequential read / write tes', False),
      Arg(
          'sequential_read_threshold', (int, float),
          'The lowest sequential read rate the device should achieve', None,
          optional=True),
      Arg(
          'sequential_write_threshold', (int, float),
          'The lowest sequential write rate the device should achieve', None,
          optional=True),
      Arg(
          'sequential_block_count', int,
          'Number of blocks to test in sequential read / write test', 1024),
      Arg('perform_locktest', bool, 'Whether to run lock test', False),
      Arg(
          'extra_prompt_en', (str, unicode),
          'An extra prompt (in English), e.g., to specify which USB port to use',
          optional=True),
      Arg(
          'extra_prompt_zh', (str, unicode), 'An extra prompt (in Chinese)',
          optional=True),
      Arg(
          'timeout_secs', int,
          'Timeout in seconds for the test to wait before it fails',
          default=20),
      Arg('bft_fixture', dict, TEST_ARG_HELP, default=None, optional=True),
      Arg(
          'skip_insert_remove', bool,
          'Skip the step of device insertion and removal', default=False),
      Arg(
          'bft_media_device', str,
          'Device name of BFT used to insert/remove the media.',
          optional=True),
      Arg(
          'usbpd_port_polarity', tuple,
          'A tuple of integers indicating (port, polarity)', optional=True),
      Arg(
          'create_partition', bool,
          'Try to create a small partition on the media. This is to check if all the pins on the '
          'sd card reader module are intact. If not specify, this test will be run for SD card.',
          default=None, optional=True)]
  # pylint: disable=E1101

  def setUp(self):
    self._dut = dut.Create()
    self._ui = test_ui.UI()
    self._template = ui_templates.TwoSections(self._ui)
    self._error = ''
    self._target_device = None
    self._device_size = None
    self._insertion_image = None
    self._removal_image = None
    self._testing_image = None
    self._locktest_insertion_image = None
    self._locktest_removal_image = None
    self._state = None
    self._total_tests = 0
    self._finished_tests = 0
    self._metrics = {}
    self._bft_fixture = None
    self._bft_media_device = None

  def tearDown(self):
    self._dut.udev.StopMonitorPath(self.args.sysfs_path)

  def GetAttrs(self, device, key_set):
    """Gets attributes of a device.

    Args:
      device: A device object.
      key_set: The attribute keys to look up.

    Returns:
      A string consisting of the specified attributes.
    """
    if device is None:
      return ''
    attrs = [device.attributes[key] for key in
             set(device.attributes.keys()) & key_set]
    attr_str = ' '.join(attrs).strip()
    if len(attr_str):
      attr_str = '/' + attr_str
    return self.GetAttrs(device.parent, key_set) + attr_str

  def GetDeviceSize(self, dev_path):
    """Gets device size in bytes.

    Args:
      dev_path: path to device file.

    Returns:
      The device size in bytes.
    """
    try:
      dev_size = self._dut.CheckOutput(['blockdev', '--getsize64', dev_path])
    except:  # pylint: disable=W0702
      self.Fail(_ERR_GET_DEV_SIZE_FAILED_FMT_STR(dev_path))

    if not dev_size:
      self.Fail(_ERR_GET_DEV_SIZE_FAILED_FMT_STR(dev_path))

    dev_size = int(dev_size)
    gb = dev_size / 1000000000.0
    logging.info('Dev size of %s : %d bytes (%.3f GB)', dev_path, dev_size, gb)

    return dev_size

  def GetDeviceRo(self, dev_path):
    """Gets device read-only flag.

    Args:
      dev_path: path to device file.

    Returns:
      A bool indicating whether RO is enabled.
    """
    try:
      ro = self._dut.CheckOutput(['blockdev', '--getro', dev_path])
    except:  # pylint: disable=W0702
      self.Fail(_ERR_RO_TEST_FAILED_FMT_STR(dev_path))

    ro = int(ro)
    logging.info('%s RO : %d', dev_path, ro)

    return ro == 1

  def GetDeviceNodeBySysPath(self, sys_path):
    """Gets device node for a storage device by given sysfs path.

    Args:
      sys_path: sysfs path for storage device.
          ex: /sys/devices/pci0000:00/0000:00:1a.0/usb1/1-1/1-1.2

    Returns:
      Device node, ex: 'sdb'. Return None if no node matched.
    """
    block_dirs = self._dut.Glob('/sys/block/sd*')
    for block_dir in block_dirs:
      if sys_path in self._dut.path.realpath(block_dir):
        return self._dut.path.basename(block_dir)
    return None

  def TestReadWrite(self):
    """Random and sequential read / write tests.

    This method executes random and / or sequential read / write test according to dargs.
    """

    def PrepareDDCommand(ifile=None, ofile=None, seek=0, skip=0, bs=None, count=None, sync=False):
      """Prepare the dd command for read / write test.

      Args:
        ifile: input file / device.
        ofile: ouput file / device.
        seek: number of blocks to be skipped from the start of the output.
        skip: number of blocks to be skipped from the start of the input.
        bs: block size in byte.
        count: number of blocks to read / write.
        sync: force sync or not.

      Returns:
        A string of command to be executed.
      """
      cmd = ['dd']
      if ifile:
        cmd.append('if=%s' % ifile)
      if ofile:
        cmd.append('of=%s' % ofile)
      if seek:
        cmd.append('seek=%d' % seek)
      if skip:
        cmd.append('skip=%d' % skip)
      if bs:
        cmd.append('bs=%d' % bs)
      if count:
        cmd.append('count=%d' % count)
      cmd = ' '.join(cmd)

      # Some board's dd tool do not support 'conv' argument to support fdatasync.
      # Use sync instead.
      if sync:
        cmd += ' && sync'
      return cmd

    self._state = _STATE_ACCESSING

    self._template.SetInstruction(_TESTING_FMT_STR(self._target_device))
    self.SetState(_IMG_HTML_TAG(self._testing_image))

    dev_path = self._target_device
    dev_size = self._device_size
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
        block_count = 1
        loop = self.args.random_block_count
        self.SetState(
            _TESTING_RANDOM_RW_FMT_STR(loop, self.args.block_size), append=True)
      elif m == _RW_TEST_MODE_SEQUENTIAL:
        # Converts block counts into bytes
        block_count = self.args.sequential_block_count
        loop = 1
        self.SetState(
            _TESTING_SEQUENTIAL_RW_FMT_STR(block_count * self.args.block_size), append=True)

      bytes_to_operate = block_count * self.args.block_size
      # Determine the range in which the random block is selected
      random_head = ((_SKIP_HEAD_SECTOR * _SECTOR_SIZE + self.args.block_size - 1) /
                     self.args.block_size)
      random_tail = ((dev_size - _SKIP_TAIL_SECTOR * _SECTOR_SIZE) /
                     self.args.block_size - block_count)

      if random_tail < random_head:
        self.Fail('Block size too large for r/w test.')

      with self._dut.temp.TempFile() as tmp_file:
        for x in range(loop):  # pylint: disable=W0612
          # Select one random block as starting point.
          random_block = random.randint(random_head, random_tail)

          dd_cmd = PrepareDDCommand(dev_path, tmp_file,
                                    bs=self.args.block_size,
                                    count=block_count,
                                    skip=random_block)
          try:
            read_start = time.time()
            self._dut.CheckCall(dd_cmd)
            read_finish = time.time()
          except Exception as e:  # pylint: disable=W0703
            factory.console.error('Failed to read block %s', e)
            ok = False
            break

          in_block = self._dut.ReadFile(tmp_file)
          if m == _RW_TEST_MODE_RANDOM:
            # Modify the first byte and write the whole block back.
            out_block = chr(ord(in_block[0]) ^ 0xff) + in_block[1:]
            self._dut.WriteFile(tmp_file, out_block)
            dd_input = tmp_file
          elif m == _RW_TEST_MODE_SEQUENTIAL:
            dd_input = '/dev/zero'
            out_block = chr(0x00) * bytes_to_operate

          dd_cmd = PrepareDDCommand(dd_input, dev_path,
                                    bs=self.args.block_size,
                                    count=block_count,
                                    seek=random_block,
                                    sync=True)
          try:
            write_start = time.time()
            self._dut.CheckCall(dd_cmd)
            write_finish = time.time()
          except Exception as e:  # pylint: disable=W0703
            factory.console.error('Failed to write block %s', e)
            ok = False
            break

          # Check if the block was actually written, and restore the
          # original content of the block.%d' % random_block]
          dd_cmd = PrepareDDCommand(ifile=dev_path,
                                    bs=self.args.block_size,
                                    count=block_count,
                                    skip=random_block)
          b = self._dut.CheckOutput(dd_cmd)
          if b != out_block:
            factory.console.error('Failed to write block')
            ok = False
            break
          self._dut.WriteFile(tmp_file, in_block)
          dd_cmd = PrepareDDCommand(tmp_file, dev_path,
                                    bs=self.args.block_size,
                                    count=block_count,
                                    seek=random_block,
                                    sync=True)
          try:
            self._dut.CheckCall(dd_cmd)
          except Exception as e:
            factory.console.error('Failed to write back block %s', e)
            ok = False
            break

          total_time_read += read_finish - read_start
          total_time_write += write_finish - write_start

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
          # pylint: disable=W0640
          update_bin['%s_speed' % test_type] = value
          logging.info('%s_speed: %.3f MB/s', test_type, value)
          if threshold:
            # pylint: disable=W0640
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

    Log(('%s_rw_speed' % self.args.media), **self._metrics)
    self._template.SetInstruction(_REMOVE_FMT_STR(self.args.media))
    self._state = _STATE_RW_TEST_WAIT_REMOVE
    self.SetState(_IMG_HTML_TAG(self._removal_image))
    if not self.args.skip_insert_remove and self._bft_fixture:
      try:
        self._bft_fixture.SetDeviceEngaged(self._bft_media_device, False)
      except BFTFixtureException as e:
        self.Fail(_ERR_BFT_ACTION_STR(
            'remove', self.args.media, self._target_device, e))

  def TestLock(self):
    """SD card write protection test."""
    self._state = _STATE_ACCESSING
    self._template.SetInstruction(_TESTING_FMT_STR(self._target_device))
    self.SetState(_IMG_HTML_TAG(self._testing_image))

    ro = self.GetDeviceRo(self._target_device)

    if ro is False:
      self._ui.FailLater(_ERR_LOCKTEST_FAILED_FMT_STR(self._target_device))
    self._template.SetInstruction(_LOCKTEST_REMOVE_FMT_STR(self.args.media))
    self._state = _STATE_LOCKTEST_WAIT_REMOVE
    self.SetState(_IMG_HTML_TAG(self._locktest_removal_image))
    self.AdvanceProgress()

  def CreatePartition(self):
    """Creates a small partition for SD card.

    This is to check if all the pins on the card reader module are intact.
    """
    if self.args.media != 'SD':
      return
    dev_path = self._target_device
    # Set partition size to 128 MB or (dev_size / 2) MB
    partition_size = min(128, (self._device_size / 2) / (1024 * 1024))
    if partition_size < _MIN_PARTITION_SIZE_MB:
      self.Fail(_ERR_CREATE_PARTITION_FMT_STR(
          self.args.media, dev_path, self._device_size))
    else:
      # clear partition table first and create one partition
      self._dut.CheckCall(['parted', '-s', dev_path, 'mklabel', 'gpt'])
      self._dut.CheckCall(['parted', '-s', dev_path, 'mkpart', 'primary',
                           'ext4', '0', str(partition_size)])

  def VerifyPartition(self):
    """Verifies the partition on target device.

    This is to verify that there is at least one partition present in the
    '/dev' directory for the device under test.
    """
    dev_path = self._target_device
    logging.info('verifying partition %s', self._target_device)
    try:
      # Just do a simple check on the first partition file
      # Auto detect parition prefix character
      if 'mmcblk' in dev_path:
        dev_path = dev_path + 'p'
      self._dut.path.exists(dev_path + '1')
    except:   # pylint: disable=W0702
      self.Fail(_ERR_VERIFY_PARTITION_FMT_STR(self.args.media, dev_path))

  def VerifyUSBPDPolarity(self):
    """Verifies the USB PD CC line polarity on the port."""
    if not self.args.usbpd_port_polarity:
      return
    port, polarity = self.args.usbpd_port_polarity
    port_status = self._dut.usb_c.GetPDStatus(port)
    if port_status['polarity'] != 'CC%d' % polarity:
      self.Fail('USB CC polarity mismatch on port %d' % port)

  def HandleUdevEvent(self, action, device):
    """The udev event handler.

    Args:
      action: The udev action to handle.
      device: A device object.
    """
    if action == self._dut.udev.Event.INSERT:
      if self._state == _STATE_RW_TEST_WAIT_INSERT:
        logging.info('%s device inserted : %s', self.args.media,
                     device.device_node)
        self._target_device = device.device_node
        self._device_size = self.GetDeviceSize(self._target_device)
        if (self.args.create_partition or
            (self.args.media == 'SD' and self.args.create_partition is None)):
          self.CreatePartition()
        self.VerifyUSBPDPolarity()
        self.TestReadWrite()

      elif self._state == _STATE_LOCKTEST_WAIT_INSERT:
        logging.info('%s device inserted : %s',
                     self.args.media, device.device_node)
        if self._target_device == device.device_node:
          if self.args.media == 'SD':
            self.VerifyPartition()
          self.TestLock()

    elif action == self._dut.udev.Event.REMOVE:
      if self._target_device == device.device_node:
        logging.info('Device removed : %s', device.device_node)
        if self._state == _STATE_RW_TEST_WAIT_REMOVE:
          if self.args.perform_locktest:
            self._template.SetInstruction(
                _LOCKTEST_INSERT_FMT_STR(self.args.media))
            self._state = _STATE_LOCKTEST_WAIT_INSERT
            self.SetState(_IMG_HTML_TAG(self._locktest_insertion_image))
          else:
            self.Pass()
        elif self._state == _STATE_LOCKTEST_WAIT_REMOVE:
          self.Pass()
        elif self._state == _STATE_ACCESSING:
          self._template.SetInstruction(
              _ERR_REMOVE_TOO_EARLY_FMT_STR(self._target_device))
          self.Fail('Device %s removed too early' % self._target_device)
        else:
          # Here the state is either _STATE_RW_TEST_WAIT_INSERT or
          # _STATE_LOCKTEST_WAIT_INSERT. For a device waiting for a media
          # getting a remove event, it probably receives duplicate media remove
          # events, ignore.
          pass

  def AdvanceProgress(self, value=1):
    """Advanced the progess bar.

    Args:
      value: The amount of progress to advance.
    """
    self._finished_tests += value
    if self._finished_tests > self._total_tests:
      self._finished_tests = self._total_tests
    self._template.SetProgressBarValue(
        100 * self._finished_tests / self._total_tests)

  def Fail(self, msg):
    """Fails the test."""
    self._ui.Fail(msg)
    raise factory.FactoryTestFailure(msg)

  def Pass(self):
    """Passes the test."""
    self._ui.Pass()

  def SetState(self, html, append=False):
    """Sets the innerHTML attribute of the state div."""
    self._ui.SetHTML(html, append=append, id=_ID_STATE_DIV)

  def runTest(self):
    """Main entrance of removable storage test."""
    random.seed(0)

    logging.info('media = %s', self.args.media)

    self._template.SetTitle(_TEST_TITLE)
    self._insertion_image = '%s_insert.png' % self.args.media
    self._removal_image = '%s_remove.png' % self.args.media
    self._testing_image = '%s_testing.png' % self.args.media

    if self.args.perform_locktest:
      self._locktest_insertion_image = ('%s_locktest_insert.png' %
                                        self.args.media)
      self._locktest_removal_image = '%s_locktest_remove.png' % self.args.media

    self._template.SetInstruction(
        _RW_TEST_INSERT_FMT_STR(
            self.args.media,
            self.args.extra_prompt_en or '',
            self.args.extra_prompt_zh or self.args.extra_prompt_en or ''))
    self._state = _STATE_RW_TEST_WAIT_INSERT
    self._template.SetState(_TEST_HTML)
    self.SetState(_IMG_HTML_TAG(self._insertion_image))

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

    # Start countdown timer.
    countdown_timer.StartCountdownTimer(
        self.args.timeout_secs,
        lambda: self.Fail('Timeout waiting for test to complete'),
        self._ui,
        _ID_COUNTDOWN_DIV)

    if self.args.skip_insert_remove:
      device_node = None
      # Poll sysfs_path is present
      timeout_time = time_utils.MonotonicTime() + self.args.timeout_secs
      while not device_node:
        device_node = self.GetDeviceNodeBySysPath(self.args.sysfs_path)
        if time_utils.MonotonicTime() > timeout_time:
          self.fail('Fail to find path: %s' % self.args.sysfs_path)
        time.sleep(0.2)
      device = self._dut.udev.Device(self._dut.path.join(self._dut.udev.GetDevBlockPath(),
                                                         device_node),
                                     self.args.sysfs_path)
      self.HandleUdevEvent(self._dut.udev.Event.INSERT, device)
      self.HandleUdevEvent(self._dut.udev.Event.REMOVE, device)
    else:
      self._dut.udev.StartMonitorPath(self.args.sysfs_path, self.HandleUdevEvent)

    # BFT engages device after udev observer start
    if not self.args.skip_insert_remove and self.args.bft_fixture:
      self._bft_fixture = CreateBFTFixture(**self.args.bft_fixture)
      self._bft_media_device = self.args.bft_media_device
      if self._bft_media_device not in self._bft_fixture.Device:
        self.fail('Invalid args.bft_media_device: ' + self._bft_media_device)
      else:
        try:
          self._bft_fixture.SetDeviceEngaged(self._bft_media_device, True)
        except BFTFixtureException as e:
          self.fail(_ERR_BFT_ACTION_STR(
              'insert', self.args.media, self._target_device, e))

    self._ui.Run()
