# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests accessing to a removable storage.

Description
-----------
Perform following tests on a removable storage device:
1. Random read/write test
2. Sequential read/write test
3. Lock (write protection) test

Test Procedure
--------------
1. Insert device (with lock switch off if there's a one)
2. Read/write test should now start. Wait for completion.
3. Remove the device

If `perform_locktest` is set, continue these steps:
4. Insert device with lock switch is on
5. Lock test should now start. Wait for completion.
6. Remove the device

If `skip_insert_remove` is set, the device should be inserted
before running this test, and the above steps 1,3,4,6 should
be skipped.

Dependency
----------
1. Use `udev` to monitor media insertion.
2. Use `parted` to initialize partitions on SD cards.
3. Use `dd` to perform read/write test.
4. Use `blockdev` to get block size and RO status.
5. Use `ectool` to check USB polarity.

Examples
--------
To do a random read/write test on 3 blocks (each for 1024 bytes) on an USB
stick, add this in test list::

  {
    "pytest_name": "removable_storage",
    "args": {
      "media": "USB",
      "sysfs_path": "/sys/devices/s5p-ehci/usb1/1-1/1-1:1.0"
    }
  }

To do a sequential read/write test on another USB port::

  {
    "pytest_name": "removable_storage",
    "args": {
      "media": "USB",
      "sysfs_path": "/sys/devices/s5p-ehci/usb1/1-2/1-2.3",
      "perform_sequential_test": true,
      "sequential_block_count": 8,
      "block_size": 524288,
      "perform_random_test": false
    }
  }

Similarly, to test a SD card::

  {
    "pytest_name": "removable_storage",
    "args": {
      "media": "SD",
      "sysfs_path": "/path/to/sd/device",
      "perform_sequential_test": true,
      "sequential_block_count": 8,
      "block_size": 524288,
      "perform_random_test": false
    }
  }

If this test can not properly find the device with a specific sysfs_path, try:

- Replace sysfs_path with its real path which comes from `realpath` command.
  For example::

    (on DUT)
    $ realpath -m /sys/bus/usb/devices/usb1/1-1/1-1.1
    > /sys/devices/platform/soc/11201000.usb/11200000.xhci/usb1/1-1/1-1.1

- Run `udevadm monitor` on DUT, plug / unplug USB devices and use paths
  shown on the screen.  For example::

    (on DUT)
    $ udevadm monitor

    (plug USB disk in)
    ...
    > UDEV  [20949.971277] add \
      /devices/platform/soc/11201000.usb/11200000.xhci/usb1/1-1/1-1.1 (usb)
    ...

..

  Notice that the path above is not actually a full real path.  Please add
  "/sys" as prefix to get the full path.
"""

from __future__ import division
from __future__ import print_function

import logging
import random
import re
import subprocess
import threading

from cros.factory.device import device_utils
from cros.factory.test.event_log import Log
from cros.factory.test import session
from cros.factory.test.fixture import bft_fixture
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils

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
_RWTestMode = type_utils.Enum(['RANDOM', 'SEQUENTIAL'])

# Minimum size required for partition test
_MIN_PARTITION_SIZE_MB = 1

_MILLION = 1000000

# Regex used for find execution time from dd output.
_RE_DD_EXECUTION_TIME = re.compile(
    r'^.* copied, ([0-9]+\.[0-9]+) s(?:econds)?, .*$', re.MULTILINE)

_Event = type_utils.Enum(['WAIT_INSERT', 'WAIT_REMOVE'])


class RemovableStorageTest(test_case.TestCase):
  """The removable storage factory test."""
  ARGS = [
      Arg('media', str,
          ('Media type. '
           'This is used for several logging messages, and to decide the icons'
           'shown on UI. Valid values are "SD" or "USB".')),
      Arg('sysfs_path', str,
          ('The expected sysfs path that udev events should come from, '
           'ex: /sys/devices/pci0000:00/0000:00:1a.0/usb1/1-1/1-1.2'),
          default=None),
      Arg('block_size', int,
          'Size of each block in bytes used in read / write test',
          default=1024),
      Arg('perform_random_test', bool,
          'Whether to run random read / write test', default=True),
      Arg('random_read_threshold', (int, float),
          'The lowest random read rate the device should achieve',
          default=None),
      Arg('random_write_threshold', (int, float),
          'The lowest random write rate the device should achieve',
          default=None),
      Arg('random_block_count', int,
          'Number of blocks to test during random read / write test',
          default=3),
      Arg('perform_sequential_test', bool,
          'Whether to run sequential read / write tes', default=False),
      Arg('sequential_read_threshold', (int, float),
          'The lowest sequential read rate the device should achieve',
          default=None),
      Arg('sequential_write_threshold', (int, float),
          'The lowest sequential write rate the device should achieve',
          default=None),
      Arg('sequential_block_count', int,
          'Number of blocks to test in sequential read / write test',
          default=1024),
      Arg('perform_locktest', bool, 'Whether to run lock test', default=False),
      Arg('timeout_secs', int,
          'Timeout in seconds for the test to wait before it fails',
          default=20),
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP, default=None),
      Arg('skip_insert_remove', bool,
          'Skip the step of device insertion and removal', default=False),
      Arg('bft_media_device', str,
          'Device name of BFT used to insert/remove the media.', default=None),
      Arg('usbpd_port_polarity', list, 'Two integers [port, polarity]',
          default=None),
      Arg('fail_check_polarity', bool,
          ('If set to True or skip_insert_remove is True, would fail the test '
           'directly when polarity is wrong. '
           'Otherwise, will prompt operator to flip the storage.'),
          default=False),
      Arg('create_partition', bool,
          ('Try to create a small partition on the media. This is to check if '
           'all the pins on the sd card reader module are intact. If not '
           'specify, this test will be run for SD card.'), default=None),
      Arg('use_busybox_dd', bool,
          ('Use busybox dd. This option can be removed when toybox dd is '
           'ready.'), default=False),
      Arg('expected_max_speed', int,
          ('The expected max speed of the device in Mpbs.'
           '480, 5000, 10000 for USB2, USB3.1 gen1, USB3.1 gen2'),
          default=None),
      i18n_arg_utils.I18nArg(
          'extra_prompt',
          'An extra prompt, e.g., to specify which USB port to use', default='')
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._errors = []
    self._target_device = None
    self._device_size = None
    self._device_speed = None
    self._metrics = {}

    random.seed(0)
    logging.info('media = %s', self.args.media)

    self._insertion_image = '%s_insert.png' % self.args.media
    self._removal_image = '%s_remove.png' % self.args.media
    self._testing_image = '%s_testing.png' % self.args.media

    self._locktest_insertion_image = '%s_locktest_insert.png' % self.args.media
    self._locktest_removal_image = '%s_locktest_remove.png' % self.args.media

    # Initialize progress bar
    total_tests = [
        self.args.perform_random_test, self.args.perform_sequential_test,
        self.args.perform_locktest
    ].count(True)
    self.ui.DrawProgressBar(total_tests)

    self.perform_read_write_test = (self.args.perform_random_test or
                                    self.args.perform_sequential_test)

    self.assertGreater(
        total_tests, 0,
        'At least one of perform_random_test, perform_sequential_test, '
        'perform_locktest should be True.')
    if self.args.skip_insert_remove:
      self.assertFalse(self.args.perform_locktest and
                       self.perform_read_write_test,
                       'Insert and remove is required if both locktest and '
                       'sequential/random test are needed.')

    self._main_test_generator = self.Run()
    self._event_handler_lock = threading.Lock()
    self._next_event = None
    self._accessing = False

    self._bft_fixture = None
    self._bft_media_device = None
    if self.args.bft_fixture:
      self._bft_fixture = bft_fixture.CreateBFTFixture(
          **self.args.bft_fixture)
      self._bft_media_device = self.args.bft_media_device
      if self._bft_media_device not in self._bft_fixture.Device:
        self.fail(
            'Invalid args.bft_media_device: %s' % self._bft_media_device)

  def tearDown(self):
    if not self.args.skip_insert_remove:
      self._dut.udev.StopMonitorPath(self.args.sysfs_path)

  def AdvanceGenerator(self):
    try:
      self._next_event = next(self._main_test_generator)
    except StopIteration:
      self.PassTask()

  def Run(self):
    if self.perform_read_write_test:
      for event in self.WaitInsert():
        yield event
      if (self.args.create_partition or
          (self.args.media == 'SD' and self.args.create_partition is None)):
        self.CreatePartition()
      if self._device_speed is not None:
        logging.info('device speed: %d Mbps', self._device_speed)
      if self.args.expected_max_speed is not None:
        if self._device_speed is None:
          self._errors.append('The device speed is unavailable.')
        elif self._device_speed != self.args.expected_max_speed:
          self._errors.append(
              'The device speed(%d Mbps) does not match the expected_max_speed'
              '(%d Mpbs)' % (self._device_speed, self.args.expected_max_speed))
      if self.args.perform_random_test:
        self.TestReadWrite(_RWTestMode.RANDOM)
      if self.args.perform_sequential_test:
        self.TestReadWrite(_RWTestMode.SEQUENTIAL)
      for event in self.WaitRemove():
        yield event

    if self.args.perform_locktest:
      for event in self.WaitLockedInsert():
        yield event
      if self.args.media == 'SD':
        self.VerifyPartition()
      self.TestLock()
      for event in self.WaitLockedRemove():
        yield event

    if self._errors:
      self.FailTask('\n'.join(self._errors))

  def HandleUdevEvent(self, action, device):
    """The udev event handler.

    Each call of the handler is run in a separate thread.

    Args:
      action: The udev action to handle.
      device: A device object.
    """
    if self._target_device is None or device.device_node == self._target_device:
      event = None
      if action == self._dut.udev.Event.INSERT:
        logging.info('Device inserted: %s', device.device_node)
        event = _Event.WAIT_INSERT
      elif action == self._dut.udev.Event.REMOVE:
        logging.info('Device removed : %s', device.device_node)
        event = _Event.WAIT_REMOVE
        if self._accessing:
          self.FailTask('Device %s removed too early' % device.device_node)
      else:
        return

      with self._event_handler_lock:
        if event == self._next_event:
          self._SetTargetDevice(device)
          self.AdvanceGenerator()

  def _SetTargetDevice(self, device):
    """Sets the target device."""
    if self._target_device is None:
      self._target_device = device.device_node
      self._device_size = self.GetDeviceSize(self._target_device)
      if self.args.media == 'USB':
        self._device_speed = self.GetUsbSpeed(device)

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
    if attr_str:
      attr_str = '/' + attr_str
    return self.GetAttrs(device.parent, key_set) + attr_str

  def GetUsbSpeed(self, device):
    """return speed(Mbps) of USB"""
    usb_device = device.find_parent('usb', 'usb_device')
    return int(usb_device.attributes.get('speed'))

  def GetDeviceSize(self, dev_path):
    """Gets device size in bytes.

    Args:
      dev_path: path to device file.

    Returns:
      The device size in bytes.
    """
    try:
      dev_size = self._dut.CheckOutput(['blockdev', '--getsize64', dev_path])
    except Exception:
      self.FailTask('Unable to determine dev size of %s.' % dev_path)

    dev_size = int(dev_size)
    gb = dev_size / 1.0e9
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
    except Exception:
      self.FailTask('Unable to get RO status of %s.' % dev_path)

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

  def _PrepareDDCommand(self, ifile=None, ofile=None, seek=0, skip=0, bs=None,
                        count=None, conv=None):
    """Prepare the dd command for read / write test.

    Args:
      ifile: input file / device.
      ofile: ouput file / device.
      seek: number of blocks to be skipped from the start of the output.
      skip: number of blocks to be skipped from the start of the input.
      bs: block size in byte.
      count: number of blocks to read / write.
      conv: additional conv argument.

    Returns:
      A string of command to be executed.
    """
    if self.args.use_busybox_dd:
      cmd = ['busybox', 'dd']
    else:
      cmd = ['dd']

    args = {
        'if': ifile, 'of': ofile, 'seek': seek, 'skip': skip,
        'bs': bs, 'count': count, 'conv': conv
    }
    for key, value in args.items():
      if value:
        cmd.append('%s=%s' % (key, value))
    return cmd

  def TestReadWrite(self, mode):
    """Random and sequential read / write tests.

    This method executes random or sequential read / write test according to
    mode.
    """
    def _GetExecutionTime(dd_output):
      """Return the execution time from the dd output."""

      match = _RE_DD_EXECUTION_TIME.search(dd_output)
      if not match:
        raise ValueError('Invalid dd output %s' % dd_output)
      return float(match.group(1))

    self._accessing = True

    self.ui.SetInstruction(_('Testing {device}...', device=self._target_device))
    self.SetImage(self._testing_image)

    dev_path = self._target_device
    dev_size = self._device_size
    ok = True
    total_time_read = 0.0
    total_time_write = 0.0

    if mode == _RWTestMode.RANDOM:
      # Read/Write one block each time
      block_count = 1
      loop_count = self.args.random_block_count
      self.SetState(
          _('Performing r/w test on {count} {bsize}-byte random blocks...',
            count=loop_count,
            bsize=self.args.block_size))
    elif mode == _RWTestMode.SEQUENTIAL:
      # Converts block counts into bytes
      block_count = self.args.sequential_block_count
      loop_count = 1
      self.SetState(
          _('Performing sequential r/w test of {bsize} bytes...',
            bsize=block_count * self.args.block_size))

    bytes_to_operate = block_count * self.args.block_size
    # Determine the range in which the random block is selected
    random_head = ((_SKIP_HEAD_SECTOR * _SECTOR_SIZE +
                    self.args.block_size - 1) // self.args.block_size)
    random_tail = ((dev_size - _SKIP_TAIL_SECTOR * _SECTOR_SIZE) //
                   self.args.block_size - block_count)

    if random_tail < random_head:
      self.FailTask('Block size too large for r/w test.')

    with self._dut.temp.TempFile() as read_buf:
      with self._dut.temp.TempFile() as write_buf:
        for unused_x in range(loop_count):
          # Select one random block as starting point.
          random_block = random.randint(random_head, random_tail)
          session.console.info(
              'Perform %s read / write test from the %dth block.',
              'random' if mode == _RWTestMode.RANDOM else 'sequential',
              random_block)

          dd_cmd = self._PrepareDDCommand(
              dev_path,
              read_buf,
              bs=self.args.block_size,
              count=block_count,
              skip=random_block)
          try:
            session.console.info('Reading %d %d-bytes block(s) from %s.',
                                 block_count, self.args.block_size, dev_path)
            output = self._dut.CheckOutput(dd_cmd, stderr=subprocess.STDOUT)
            read_time = _GetExecutionTime(output)
          except Exception as e:
            session.console.error('Failed to read block %s', e)
            ok = False
            break

          # Prepare the data for writing.
          if mode == _RWTestMode.RANDOM:
            self._dut.CheckCall(['cp', read_buf, write_buf])
            # Modify the first byte.
            dd_cmd = self._PrepareDDCommand(write_buf, bs=1, count=1)
            first_byte = ord(self._dut.CheckOutput(dd_cmd, stderr=None))
            first_byte ^= 0xff
            with self._dut.temp.TempFile() as tmp_file:
              self._dut.WriteFile(tmp_file, chr(first_byte))
              dd_cmd = self._PrepareDDCommand(
                  tmp_file, write_buf, bs=1, count=1, conv='notrunc')
              self._dut.CheckCall(dd_cmd)
          elif mode == _RWTestMode.SEQUENTIAL:
            dd_cmd = self._PrepareDDCommand(
                '/dev/zero',
                write_buf,
                bs=self.args.block_size,
                count=block_count)
            self._dut.CheckCall(dd_cmd)

          dd_cmd = self._PrepareDDCommand(
              write_buf,
              dev_path,
              bs=self.args.block_size,
              count=block_count,
              seek=random_block,
              conv='fsync')
          try:
            session.console.info('Writing %d %d-bytes block(s) to %s.',
                                 block_count, self.args.block_size, dev_path)
            output = self._dut.CheckOutput(dd_cmd, stderr=subprocess.STDOUT)
            write_time = _GetExecutionTime(output)
          except Exception as e:
            session.console.error('Failed to write block %s', e)
            ok = False
            break

          # Check if the block was actually written, and restore the
          # original content of the block.
          dd_cmd = self._PrepareDDCommand(
              ifile=dev_path,
              bs=self.args.block_size,
              count=block_count,
              skip=random_block)
          try:
            self._dut.CheckCall(
                ' '.join(dd_cmd) + ' | toybox cmp %s -' % write_buf)
          except Exception as e:
            session.console.error('Failed to write block %s', e)
            ok = False
            break

          dd_cmd = self._PrepareDDCommand(
              read_buf,
              dev_path,
              bs=self.args.block_size,
              count=block_count,
              seek=random_block,
              conv='fsync')
          try:
            self._dut.CheckCall(dd_cmd)
          except Exception as e:
            session.console.error('Failed to write back block %s', e)
            ok = False
            break

          total_time_read += read_time
          total_time_write += write_time

    self.SetState('')
    self._accessing = False
    self.ui.AdvanceProgress()

    if not ok:
      if self.GetDeviceRo(dev_path):
        session.console.warn('Is write protection on?')
        self._errors.append('%s is read-only.' % dev_path)
      else:
        test_name = ''
        if mode == _RWTestMode.RANDOM:
          test_name = 'random r/w'
        elif mode == _RWTestMode.SEQUENTIAL:
          test_name = 'sequential r/w'
        self._errors.append('IO error while running %s test on %s.' %
                            (test_name, self._target_device))
    else:
      update_bin = {}

      def _CheckThreshold(test_type, value, threshold):
        update_bin['%s_speed' % test_type] = value
        logging.info('%s_speed: %.3f MB/s', test_type, value)
        if threshold:
          update_bin['%s_threshold' % test_type] = threshold
          if value < threshold:
            self._errors.append('%s_speed of %s does not meet lower bound.' %
                                (test_type, self._target_device))

      if mode == _RWTestMode.RANDOM:
        random_read_speed = (
            (self.args.block_size * loop_count) / total_time_read / _MILLION)
        random_write_speed = (
            (self.args.block_size * loop_count) / total_time_write / _MILLION)
        _CheckThreshold('random_read', random_read_speed,
                        self.args.random_read_threshold)
        _CheckThreshold('random_write', random_write_speed,
                        self.args.random_write_threshold)
      elif mode == _RWTestMode.SEQUENTIAL:
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

  def TestLock(self):
    """SD card write protection test."""
    self._accessing = True
    self.ui.SetInstruction(_('Testing {device}...', device=self._target_device))
    self.SetImage(self._testing_image)

    if not self.GetDeviceRo(self._target_device):
      self._errors.append('Locktest failed on %s.' % self._target_device)

    self._accessing = False
    self.ui.AdvanceProgress()

  def CreatePartition(self):
    """Creates a small partition for SD card.

    This is to check if all the pins on the card reader module are intact.
    """
    if self.args.media != 'SD':
      return
    dev_path = self._target_device
    # Set partition size to 128 MB or (dev_size / 2) MB
    partition_size = min(128, (self._device_size // 2) // (1024 * 1024))
    if partition_size < _MIN_PARTITION_SIZE_MB:
      self.FailTask('The size on %s device %s is too small (only %d bytes) for '
                    'partition test.' % (self.args.media, dev_path,
                                         self._device_size))
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
      # Auto detect partition prefix character
      if 'mmcblk' in dev_path:
        dev_path = dev_path + 'p'
      self._dut.path.exists(dev_path + '1')
    except Exception:
      self.FailTask(
          'Partition verification failed on %s device %s. Problem with card '
          'reader module maybe?' % (self.args.media, dev_path))

  def CheckUSBPDPolarity(self):
    """Verifies the USB PD CC line polarity on the port."""
    if not self.args.usbpd_port_polarity:
      return True
    port, polarity = self.args.usbpd_port_polarity
    port_status = self._dut.usb_c.GetPDStatus(port)
    return port_status['polarity'] == 'CC%d' % polarity

  def FixtureCommand(self, mode):
    """Command the fixture.

    Args:
      mode: Mode of operation, should be either 'insert' or 'remove'.
    """
    try:
      self._bft_fixture.SetDeviceEngaged(self._bft_media_device,
                                         mode == 'insert')
    except bft_fixture.BFTFixtureException as e:
      self.fail('BFT fixture failed to %s %s device %s. Reason: %s' %
                (mode, self.args.media, self._target_device, e))

  def WaitInsert(self):
    """Wait for the removable storage to be inserted.

    Yields the event that it is waiting.
    """
    if self.args.skip_insert_remove:
      device_node = sync_utils.WaitFor(
          lambda: self.GetDeviceNodeBySysPath(self.args.sysfs_path),
          self.args.timeout_secs)
      device = self._dut.udev.Device(
          self._dut.path.join(self._dut.udev.GetDevBlockPath(), device_node),
          self.args.sysfs_path)
      self._SetTargetDevice(device)
      # If skip_insert_remove is True, would fail the test directly when
      # polarity is wrong.
      if not self.CheckUSBPDPolarity():
        self.FailTask('USB CC polarity mismatch.')
    else:
      if self._bft_fixture:
        self.FixtureCommand('insert')

      while True:
        self.ui.SetInstruction(
            _('Insert {media} drive for read/write test... {extra}<br>'
              'WARNING: DATA ON INSERTED MEDIA WILL BE LOST!',
              media=self.args.media,
              extra=self.args.extra_prompt))
        self.SetImage(self._insertion_image)
        yield _Event.WAIT_INSERT
        if self.CheckUSBPDPolarity():
          return
        if self.args.fail_check_polarity:
          self.FailTask('USB CC polarity mismatch.')
        else:
          self.ui.SetInstruction(
              _('Wrong USB side, please flip over {media}.',
                media=self.args.media))
          self.SetImage(self._removal_image)
          yield _Event.WAIT_REMOVE

  def WaitRemove(self):
    """Wait for the removable storage to be removed.

    Yields the event that it is waiting.
    """
    if self.args.skip_insert_remove:
      return

    if self._bft_fixture:
      self.FixtureCommand('remove')

    self.ui.SetInstruction(_('Remove {media} drive...', media=self.args.media))
    self.SetImage(self._removal_image)
    yield _Event.WAIT_REMOVE

  def WaitLockedInsert(self):
    """Wait for the removable storage to be inserted before lock test.

    Yields the event that it is waiting.
    """
    if self.args.skip_insert_remove:
      return

    if self._bft_fixture:
      self.FixtureCommand('insert')

    self.ui.SetInstruction(
        _('Toggle lock switch and insert {media} drive again...',
          media=self.args.media))
    self.SetImage(self._locktest_insertion_image)
    yield _Event.WAIT_INSERT

  def WaitLockedRemove(self):
    """Wait for the removable storage to be removed after lock test.

    Yields the event that it is waiting.
    """
    if self.args.skip_insert_remove:
      return

    if self._bft_fixture:
      self.FixtureCommand('remove')

    self.ui.SetInstruction(
        _('Remove {media} drive and toggle lock switch...',
          media=self.args.media))
    self.SetImage(self._locktest_removal_image)
    yield _Event.WAIT_REMOVE

  def SetState(self, html):
    """Sets the innerHTML attribute of the state div."""
    self.ui.SetHTML(html, id='state')

  def SetImage(self, url):
    """Sets the image src."""
    self.ui.RunJS('document.getElementById("image").src = args.url;', url=url)

  def runTest(self):
    """Main entrance of removable storage test."""
    self.ui.StartFailingCountdownTimer(self.args.timeout_secs)

    if not self.args.skip_insert_remove:
      self._dut.udev.StartMonitorPath(
          self.args.sysfs_path,
          self.event_loop.CatchException(self.HandleUdevEvent))

    # This may block if self.args.skip_insert_remove is True, so we need to run
    # it in another thread.
    process_utils.StartDaemonThread(
        target=self.event_loop.CatchException(self.AdvanceGenerator))
    self.WaitTaskEnd()
