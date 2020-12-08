# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests a storage device by running the badblocks command.

Description
-----------
This test uses ``badblocks(8)`` command to search for badblocks on a device.  By
default the unused portion of the stateful partition is used
(``mode=stateful_partition_free_space``).  (For instance, on
a device with a 32 GB hard drive, cgpt reports that partition 1 is about 25 GB,
but the size of the filesystem is only about 1 GB.  We run the test on the
unused 24 GB.)

Alternatively one can specify the use of a file in the filesystem allocated by
the test, or raw mode where a specific file/partition must be provided.
(``mode=file`` or ``mode=raw``)

When ``mode=stateful_partition_free_space``, unused portion after stateful
partition must exist.  An error message ``'There is no unused space after
stateful partition.'`` will be shown if it cannot find any extra space.
(If you install the image by ``chromeos-install``, by default, there will be no
free space after stateful partition.)

Test Procedure
--------------
This test does not require operator interaction.  An UI will be shown to
indicate the process of testing.

Dependency
----------
This pytest depends on ``badblocks(8)``.

Examples
--------
This pytest is defined as ``BadBlocks`` in ``generic_common.test_list.json``.
It will use **unused portion of the stateful partition** for testing.  It will
test for 1 GB of space.  On most devices, ``badblocks`` takes ~0.5s/MB (for four
passes).  So the default setup will take about 9 minutes.  Normally you only
want to override ``max_bytes`` in your test list.  For example, to change it to
2 GB::

  "definitions": {
    "BadBlocks": {
      "args": {
        "max_bytes": 2147483648
      }
    }
  }

Troubleshooting
---------------
If the test image is installed by `chromeos-install` and pytest complains
there's no unused space to be checked, re-install the image via factory shim
or netboot.  You can find different ways to install images at here:
https://chromium.googlesource.com/chromiumos/platform/factory/+/HEAD/README.md#Imaging-methods
"""

from collections import namedtuple
import logging
import re
from select import select
import subprocess
import tempfile
import time

from cros.factory.device import device_utils
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils


_TestModes = type_utils.Enum(['file', 'raw', 'stateful_partition_free_space'])


class BadBlocksTest(test_case.TestCase):
  ARGS = [
      Arg('mode', _TestModes, 'Specify which operating mode to use.',
          default=_TestModes.stateful_partition_free_space),
      Arg('device_path', str, 'Override the device path on which to test. '
          'Also functions as a file path for file and raw modes.',
          default=None),
      Arg('max_bytes', int, 'Maximum size to test, in bytes.',
          default=None),
      Arg('max_errors', int, 'Stops testing after the given number of errors.',
          default=20),
      Arg('timeout_secs', (int, float), 'Timeout in seconds for progress lines',
          default=10),
      Arg('extra_log_cmd', str,
          'Extra command to run at start/finish to collect logs.',
          default=None),
      Arg('log_threshold_secs', (int, float),
          'If no badblocks output is detected for this long, log an error '
          'but do not fail',
          default=5),
      Arg('log_interval_secs', int,
          'The interval between progress logs in seconds.',
          default=60),
      Arg('drop_caches_interval_secs', int,
          'The interval between dropping caches in seconds.',
          default=120),
      Arg('destructive', bool,
          'Do desctructive read / write test. If set to False, '
          'the data will be kept after testing, but longer testing time is '
          'expected.',
          default=True),
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

    # A process that monitors /var/log/messages file.
    self.message_monitor = None

    self.CheckArgs()

    # TODO(bhthompson): refactor this for a better device type detection.
    if self.args.mode == _TestModes.file:
      unused_mount_on, self._filesystem = self.dut.storage.GetMountPoint(
          self.args.device_path)
    else:
      self._filesystem = self.args.device_path

    # If 'mmcblk' in self._filesystem assume we are eMMC.
    self._is_mmc = 'mmcblk' in self._filesystem

    self.current_phase = 0

    # Group checker for Testlog.
    self.command_group_checker = testlog.GroupParam(
        'log_command', ['command', 'command_stdout', 'command_stderr'])
    testlog.UpdateParam('command', param_type=testlog.PARAM_TYPE.argument)
    self.sata_link_info_group_checker = testlog.GroupParam(
        'sata_link_info', ['sata_link_speed', 'system_log_message', 'phase'])

  def tearDown(self):
    # Sync, so that any problems (like writing outside of our partition)
    # will show up sooner rather than later.
    self._LogSmartctl()
    self.dut.Call(['sync'])
    if self.args.mode == _TestModes.file:
      self.dut.Call(['rm', '-f', self.args.device_path])
    if self.message_monitor:
      self.message_monitor.kill()
      self.message_monitor = None

  def CheckArgs(self):
    if self.args.max_bytes:
      # We don't want to try running bad blocks on <1kB
      self.assertGreaterEqual(self.args.max_bytes, 1024, 'max_bytes too small.')
    if self.args.device_path is None:
      if self.args.mode == _TestModes.raw:
        raise ValueError('In raw mode the device_path must be specified.')
      self.args.device_path = self.dut.storage.GetMainStorageDevice()
    if self.args.mode == _TestModes.file:
      if self.args.device_path.startswith('/dev/'):
        # In file mode we want to use the filesystem, not a device node,
        # so we default to the stateful partition.
        self.args.device_path = '/mnt/stateful_partition/temp_badblocks_file'
      if self.args.max_bytes is None:
        # Default to 100MB file size for testing.
        self.args.max_bytes = 100 * 1024 * 1024
      # Add in a file extension, to ensure we are only using our own file.
      self.args.device_path = self.args.device_path + '.for_bad_blocks_test'
      self.args.max_bytes = self._GenerateTestFile(self.args.device_path,
                                                   self.args.max_bytes)

  def DetermineParameters(self):
    first_block = 0
    sector_size = 1024
    if self.args.mode == _TestModes.file:
      last_block = self.args.max_bytes // sector_size
      logging.info('Using a generated file at %s, size %dB, sector size %dB, '
                   'last block %d.', self.args.device_path, self.args.max_bytes,
                   sector_size, last_block)
    elif self.args.mode == _TestModes.raw:
      # For some files like dev nodes we cannot trust the stats provided by
      # the os, so we manually seek to the end of the file to determine size.
      raw_file_bytes = self.dut.path.getsize(self.args.device_path)
      if self.args.max_bytes is None or self.args.max_bytes > raw_file_bytes:
        logging.info('Setting max_bytes to the available size of %dB.',
                     raw_file_bytes)
        self.args.max_bytes = raw_file_bytes
      if self.args.device_path.startswith('/dev/'):
        partitions = sys_utils.PartitionManager(self.args.device_path, self.dut)
        sector_size = partitions.GetSectorSize()
      last_block = self.args.max_bytes // sector_size
      logging.info('Using an existing file at %s, size %dB, sector size %dB, '
                   'last block %d.', self.args.device_path, self.args.max_bytes,
                   sector_size, last_block)
    elif self.args.mode == _TestModes.stateful_partition_free_space:
      part_prefix = 'p' if self.args.device_path[-1].isdigit() else ''
      # Always partition 1
      partition_path = '%s%s1' % (self.args.device_path, part_prefix)

      # Determine total length of the FS
      dumpe2fs = self.dut.CheckOutput(['dumpe2fs', '-h', partition_path],
                                      log=True)
      logging.info('Filesystem info for  header:\n%s', dumpe2fs)

      fields = dict(re.findall(r'^(.+):\s+(.+)$', dumpe2fs, re.MULTILINE))
      fs_first_block = int(fields['First block'])
      fs_block_count = int(fields['Block count'])
      fs_block_size = int(fields['Block size'])

      partitions = sys_utils.PartitionManager(self.args.device_path, self.dut)
      partition_index = 1
      start_sector = partitions.GetPartitionOffsetInSector(partition_index)
      sector_count = partitions.GetPartitionSizeInSector(partition_index)
      sector_size = partitions.GetSectorSize()

      # Could get this to work, but for now we assume that fs_block_size is a
      # multiple of sector_size.
      self.assertEqual(0, fs_block_size % sector_size,
                       'fs_block_size %d is not a multiple of sector_size %d' %
                       (fs_block_size, sector_size))

      first_unused_sector = (fs_first_block + fs_block_count) * (
          fs_block_size // sector_size)
      first_block = first_unused_sector + start_sector
      sectors_to_test = sector_count - first_unused_sector
      if self.args.max_bytes:
        sectors_to_test = min(sectors_to_test,
                              self.args.max_bytes // sector_size)
      last_block = first_block + sectors_to_test - 1

      local_variables = locals()
      logging.info(', '.join(
          ['%s=%s' % (x, local_variables[x])
           for x in ['fs_first_block', 'fs_block_count', 'fs_block_size',
                     'start_sector', 'sector_count',
                     'sector_size',
                     'first_unused_sector',
                     'sectors_to_test',
                     'first_block',
                     'last_block']]))

      fail_desc = 'There is no unused space after stateful partition.'
      if sectors_to_test <= 0:
        session.console.error(
            fail_desc + ' Was the OS installed by `chromeos-install`?' +
            ' You should image the device via factory install shim or netboot.'
            + ' See "Troubleshooting" in pytest header for detail.')
      self.assertGreaterEqual(last_block, first_block, fail_desc)
    else:
      raise ValueError('Invalid mode selected, check test_list mode setting.')

    Parameters = namedtuple('Parameters', ('first_block last_block sector_size '
                                           'device_path max_errors'))
    return Parameters(first_block, last_block, sector_size,
                      self.args.device_path, self.args.max_errors)

  def runTest(self):
    self.assertFalse(sys_utils.InChroot(),
                     'badblocks test may not be run within the chroot')

    params = self.DetermineParameters()

    test_size_mb = '%.1f MiB' % (
        (params.last_block - params.first_block + 1) *
        params.sector_size / 1024 ** 2)

    self.ui.SetInstruction(
        _('Testing {test_size_mb} region of storage',
          test_size_mb=test_size_mb))

    # Kill any badblocks processes currently running
    self.dut.Call(['killall', 'badblocks'])

    # -f = force (since the device may be in use)
    # -s = show progress
    # -v = verbose (print error count)
    # -w = destructive write+read test
    # -n = non-destructive write+read test
    args = '-fsv'
    args += 'w' if self.args.destructive else 'n'
    process = self.dut.Popen(
        ['badblocks', args, '-b', str(params.sector_size)] +
        (['-e', str(params.max_errors)] if params.max_errors else []) +
        [params.device_path, str(params.last_block), str(params.first_block)],
        log=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    # The total number of phases there will be (8: read and write for each
    # of 4 different patterns).
    total_phases = 8

    self.ui.DrawProgressBar(total_phases)

    # The phase we're currently in (0-relative).
    self.current_phase = 0

    # How far we are through the current phase.
    fraction_within_phase = 0

    buf = []
    lines = []

    self._UpdateSATALinkSpeed()
    self._LogSmartctl()

    def UpdatePhase():
      event_log.Log('start_phase', current_phase=self.current_phase)
      self.ui.SetHTML(
          _('Phase {current_phase}/{total_phases}: ',
            current_phase=min(self.current_phase + 1, total_phases),
            total_phases=total_phases),
          id='bb-phase')
    UpdatePhase()

    last_drop_caches_time = last_log_time = time.time()
    while True:
      # Assume no output in timeout_secs means hung on disk op.
      start_time = time.time()
      rlist, unused_wlist, unused_xlist = select(
          [process.stdout], [], [], self.args.timeout_secs)
      end_time = time.time()
      self._UpdateSATALinkSpeed()

      if end_time - start_time > self.args.log_threshold_secs:
        session.console.warn('Delay of %.2f s between badblocks progress lines',
                             end_time - start_time)
        event_log.Log('delay', duration_secs=end_time - start_time)
        testlog.LogParam('delay', end_time - start_time)

      self.assertTrue(
          rlist,
          'Timeout: No badblocks output for %.2f s' % self.args.timeout_secs)

      ch = process.stdout.read(1)
      if ch in ['', '\x08', '\r', '\n']:
        line = ''.join(buf).strip()
        if line:
          # Log if this is not a progress line or log_interval_secs has passed
          # since last log line.
          match = re.match(r'([.0-9]+)% done, ', line)
          log_elapsed_time = time.time() - last_log_time
          if not match or log_elapsed_time > self.args.log_interval_secs:
            last_log_time = time.time()
            logging.info('badblocks> %s', line)

          match = re.search(r'([.0-9]+)% done, ', line)
          if match:
            # The percentage reported is actually the percentage until the last
            # block; convert it to an offset within the current phase.
            block_offset = (
                float(match.group(1)) / 100) * (params.last_block + 1)
            fraction_within_phase = (block_offset - params.first_block) / (
                params.last_block + 1 - params.first_block)
            self.ui.SetHTML(line[match.end():], id='bb-progress')
            line = line[:match.start()].strip()  # Remove percentage from status

          line = line.rstrip(':')

          if line and line != 'done':
            self.ui.SetHTML(test_ui.Escape(line), id='bb-status')

          # Calculate overall percentage done.
          phases_done = self.current_phase + max(0, fraction_within_phase)
          self.ui.SetProgress(phases_done)

          if line.startswith('done'):
            self.current_phase += 1
            UpdatePhase()
            fraction_within_phase = 0
          lines.append(line)

        if ch == '':
          break
        buf = []

        # See if we shuold drop caches.
        if (self.args.drop_caches_interval_secs and
            (time.time() - last_drop_caches_time >
             self.args.drop_caches_interval_secs)):
          logging.info('Dropping caches')
          self.dut.WriteFile('/proc/sys/vm/drop_caches', '1')
          last_drop_caches_time = time.time()
      else:
        buf.append(ch)

    self.assertEqual(
        0, process.wait(),
        'badblocks returned with error code %d' % process.returncode)

    last_line = lines[-1]
    self.assertEqual('Pass completed, 0 bad blocks found. (0/0/0 errors)',
                     last_line)

  def _GenerateTestFile(self, file_path, file_bytes):
    """Generate a sparse file for testing of a given size.

    Args:
      file_path: String of the path to the file to generate.
      file_bytes: Int of the number of bytes to generate.

    Returns:
      Int of the number of bytes actually allocated.

    Raises:
      Assertion if the containing folder does not exist.
      Assertion if the filesystem does not have adequate space.
    """
    folder = self.dut.path.dirname(file_path)
    self.assertTrue(self.dut.path.isdir(folder), 'Folder does not exist.')

    stat = self.dut.CheckOutput(['stat', '-f', '-c', '%a|%s', folder])
    (available_blocks, block_size) = map(int, stat.split('|'))
    free_bytes = available_blocks * block_size
    logging.info('Detected %dB free space at %s', free_bytes, folder)
    # Assume we want at least 10MB free on the file system, so we make a pad.
    pad = 10 * 1024 * 1024
    if file_bytes > free_bytes + pad:
      logging.warning('The file size is too large for the file system, '
                      'clipping file to %dB.', free_bytes - pad)
      file_bytes = free_bytes - pad
    self.dut.Call(['truncate', '-s', str(file_bytes), file_path], log=True)
    return file_bytes

  def _LogSmartctl(self):
    # No smartctl on mmc.
    # TODO (cychiang) crosbug.com/p/17146. We need to find a replacement
    # of smartctl for mmc.
    if self._is_mmc:
      return

    if self.args.extra_log_cmd:
      try:
        process = self.dut.Popen(
            self.args.extra_log_cmd, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, log=True)
      except NotImplementedError:
        # ADBLink can't separate stderr and stdout to different PIPE
        process = self.dut.Popen(
            self.args.extra_log_cmd, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, log=True)

      stdout_data, stderr_data = process.communicate()

      if stdout_data:
        logging.info('stdout:\n%s', stdout_data)
      if stderr_data:
        logging.info('stderr:\n%s', stderr_data)
      event_log.Log('log_command', command=self.args.extra_log_cmd,
                    stdout=stdout_data, stderr=stderr_data)
      with self.command_group_checker:
        testlog.LogParam('command', self.args.extra_log_cmd)
        testlog.LogParam('command_stdout', stdout_data)
        testlog.LogParam('command_stderr', stderr_data)

    cmd = ['smartctl', '-a', self._filesystem]
    with tempfile.TemporaryFile('w+') as stdout:
      exit_code = self.dut.Call(cmd, stdout=stdout)
      stdout.flush()
      stdout.seek(0)
      smartctl_output = stdout.read()

    logging.info('smartctl output: %s', smartctl_output)
    event_log.Log('smartctl', stdout=smartctl_output)
    testlog.LogParam('smartctl', smartctl_output)

    self.assertTrue(
        'SMART overall-health self-assessment test result: PASSED'
        in smartctl_output,
        'SMART says drive is not healthy')
    # Ignore error other than first two bits, this should be aligned to
    # hardware_Smartctl autotest.
    self.assertTrue(
        exit_code & 0x3 == 0, 'smartclt exit code = 0x%x' % exit_code)

  def _UpdateSATALinkSpeed(self):
    """Updates the current SATA link speed based on /var/log/messages."""
    # No SATA on mmc.
    if self._is_mmc:
      return

    first_time = self.message_monitor is None
    if first_time:
      self.message_monitor = self.dut.Popen(['tail', '-f', '/var/log/messages'],
                                            stdin=open('/dev/null'),
                                            stdout=subprocess.PIPE)

    # List of dicts to log.
    link_info_events = []

    if first_time:
      rlist, unused_wlist, unused_xlist = select(
          [self.message_monitor.stdout], [], [], self.args.timeout_secs)
      if not rlist:
        logging.warning('UpdateSATALinkSpeed: Cannot get any line from '
                        '/var/log/messages after %d seconds',
                        self.args.timeout_secs)

    while True:
      rlist, unused_wlist, unused_xlist = select(
          [self.message_monitor.stdout], [], [], 0)
      if not rlist:
        break
      log_line = self.message_monitor.stdout.readline()
      if not log_line:  # this shouldn't happen
        break
      log_line = log_line.strip()
      match = re.match(r'(\S)+.+SATA link up ([0-9.]+) (G|M)bps', log_line)
      if match:
        sata_link_speed_mbps = (
            int(float(match.group(2)) *
                (1000 if match.group(3) == 'G' else 1)))
        link_info_events.append(dict(speed_mbps=sata_link_speed_mbps,
                                     log_line=log_line))

      # Copy any ATA-related messages to the test log, and put in event logs.
      if not first_time and re.search(r'\bata[0-9.]+:', log_line):
        logging.info('System log message: %s', log_line)
        event_log.Log('system_log_message', log_line=log_line)
        with self.sata_link_info_group_checker:
          testlog.LogParam('system_log_message', log_line)
          testlog.LogParam('phase', self.current_phase)
          testlog.LogParam('sata_link_speed', None)

    if first_time and link_info_events:
      # First time, ignore all but the last
      link_info_events = link_info_events[-1:]

    for event in link_info_events:
      logging.info('SATA link info: %r', event)
      event_log.Log('sata_link_info', **event)
      with self.sata_link_info_group_checker:
        testlog.LogParam('system_log_message', event['log_line'])
        testlog.LogParam('phase', self.current_phase)
        testlog.LogParam('sata_link_speed', event['speed_mbps'])
