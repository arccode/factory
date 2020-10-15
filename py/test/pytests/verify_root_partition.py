# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Verifies the integrity of the root partition."""

import logging
import os
import re
import tempfile

from cros.factory.device import device_utils
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg


DM_DEVICE_NAME = 'verifyroot'
DM_DEVICE_PATH = os.path.join('/dev/mapper', DM_DEVICE_NAME)
BLOCK_SIZE = 8 * 1024 * 1024


class VerifyRootPartitionTest(test_case.TestCase):
  """Verifies the integrity of the root partition."""

  ARGS = [
      Arg('kern_a_device', str,
          'Path to the device containing KERN-A partition', default=None),
      Arg('root_device', str,
          'Path to the device containing rootfs partition', default=None),
      Arg('max_bytes', int, 'Maximum number of bytes to read', default=None),
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def runTest(self):
    if not self.args.kern_a_device:
      self.args.kern_a_device = self.dut.partitions.RELEASE_KERNEL.path
    if not self.args.root_device:
      self.args.root_device = self.dut.partitions.RELEASE_ROOTFS.path

    # Prepend '/dev/' if the device path is not absolute. This is mainly for
    # backward-compatibility as many existing test list specifies only 'sda4' or
    # 'mmcblk0p4' in dargs.
    if not self.args.kern_a_device.startswith('/'):
      self.args.kern_a_device = os.path.join('/dev', self.args.kern_a_device)
    if not self.args.root_device.startswith('/'):
      self.args.root_device = os.path.join('/dev', self.args.root_device)

    # Copy out the KERN-A partition to a file, since vbutil_kernel
    # won't operate on a device, only a file
    # (http://crosbug.com/34176)
    self.ui.SetState('Verifying KERN-A (%s)...' % self.args.kern_a_device)
    with self.dut.temp.TempFile() as kern_a_bin:
      self.dut.toybox.dd(if_=self.args.kern_a_device, of=kern_a_bin,
                         conv='fsync')
      try:
        vbutil_kernel_output = self.dut.CheckOutput(
            ['futility', 'vbutil_kernel', '--verify', kern_a_bin, '--verbose'],
            log=True)
      except Exception:
        logging.exception(
            'Unable to verify kernel in KERN-A; perhaps this device was imaged '
            'with chromeos-install instead of factory server?')
        raise

    logging.info('vbutil_kernel output is:\n%s', vbutil_kernel_output)

    DM_REGEXP = re.compile(r'dm="(?:1 )?vroot none ro(?: 1)?,(0 (\d+) .+)"')
    match = DM_REGEXP.search(vbutil_kernel_output)
    assert match, 'Cannot find regexp %r in vbutil_kernel output' % (
        DM_REGEXP.pattern)

    table = match.group(1)
    partition_size = int(match.group(2)) * 512

    DEV_REGEXP = re.compile(r'payload=\S* hashtree=\S*')
    (table_new, nsubs) = DEV_REGEXP.subn(
        'payload=%s hashtree=%s' % (
            self.args.root_device, self.args.root_device), table)
    assert nsubs == 1, ('Expected to find %r in %r once, '
                        'but found %d matches.' %
                        (DEV_REGEXP.pattern, table, nsubs))
    table = table_new
    del table_new
    # Cause I/O error on invalid bytes
    table += ' error_behavior=eio'

    # Remove device in case a previous test left it hanging
    self._RemoveDMDevice()
    assert not self.dut.path.exists(DM_DEVICE_PATH)
    # Map the device
    self.dut.CheckCall(
        ['dmsetup', 'create', '-r', DM_DEVICE_NAME, '--table', table], log=True)

    # Read data from the partition; there will be an I/O error on failure
    if self.args.max_bytes is None:
      bytes_to_read = partition_size
    else:
      bytes_to_read = min(partition_size, self.args.max_bytes)

    if self.dut.link.IsLocal():
      self.ui.DrawProgressBar(bytes_to_read)
      # For local link, let's show progress bar for better UX
      with open(DM_DEVICE_PATH, 'rb') as dm_device:
        bytes_read = 0
        while True:
          bytes_left = bytes_to_read - bytes_read
          if not bytes_left:
            break
          count = len(dm_device.read(min(BLOCK_SIZE, bytes_left)))
          if not count:
            break
          bytes_read += count
          pct_done = bytes_read / bytes_to_read
          message = 'Read {:.1f} MiB ({:.1%}) of {}'.format(
              bytes_read / 1024 / 1024, pct_done, self.args.root_device)
          logging.info(message)
          self.ui.SetState(message)
          self.ui.SetProgress(bytes_read)
    else:
      # for remote link, read out everything at once to save time.
      with tempfile.TemporaryFile('w+') as stderr:
        try:
          # since we need the output of stderr, use CheckCall rather than
          # toybox.dd
          self.dut.CheckCall(
              ['dd', 'if=' + DM_DEVICE_PATH, 'of=/dev/null',
               'bs=%d' % BLOCK_SIZE, 'count=%d' % bytes_to_read,
               'iflag=count_bytes'],
              log=True, stderr=stderr)
          stderr.flush()
          stderr.seek(0)
          dd_output = stderr.read()
        except Exception:
          stderr.flush()
          stderr.seek(0)
          logging.error('verify rootfs failed: %s', stderr.read())
          raise

      DD_REGEXP = re.compile(r'^(\d+) bytes \(.*\) copied', re.MULTILINE)
      match = DD_REGEXP.search(dd_output)
      assert match, 'unexpected dd output: %s' % dd_output
      bytes_read = int(match.group(1))

    self.assertEqual(bytes_to_read, bytes_read)

  def tearDown(self):
    self._RemoveDMDevice()

  def _RemoveDMDevice(self):
    self.dut.Call(['dmsetup', 'remove', DM_DEVICE_NAME], log=True)
