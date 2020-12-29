#!/usr/bin/env python3
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
from collections import namedtuple
import contextlib
from glob import glob
from itertools import chain
import logging
import os
import stat
import sys

from cros.factory.test.env import paths as env_paths
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils import sys_utils


# The candidate of device names which the ChromeOS may mount on rootfs.
# Assume that ChromeOS has only one device, and always has a smaller index.
# That is, it should always be `sda`, `nvme0n1`... not `sdb`, `nvme0n2`...
ROOT_DEV_NAME_CANDIDATE = ['sda', 'nvme0n1', 'mmcblk0']

# Root directory to use when root partition is USB
USB_ROOT_OUTPUT_DIR = '/mnt/stateful_partition/factory_bug'

DESCRIPTION = """Generate and save zip archive of log files.

  This tool always tries to collect log from the on board storage device.
  That is, if the current rootfs is a removable devices like usb drive,
  this tool will try to find the on board device and collect log from it.
"""

EXAMPLES = """Examples:

  When booting from the internal hard disk:

    # Save logs to /tmp
    factory_bug

    # Save logs to a USB drive (using the first one already mounted, or the
    # first mountable on any USB device if none is mounted yet)
    factory_bug --save-to-removable

  When booting from an USB drive:

    # Mount on board rootfs, collect logs from there, and save logs to the USB
    # drive's stateful partition
    factory_bug

    # Specify the input device for logs collecting.
    factory_bug --input-device /dev/sda
"""

# Info about a mounted partition.
#
# Properties:
#   dev: The device that was mounted or re-used.
#   mount_point: The mount point of the device.
#   temporary: Whether the device is being temporarily mounted.
MountUSBInfo = namedtuple('MountUSBInfo', ['dev', 'mount_point', 'temporary'])


def GetRootDevice():
  """Get the device name on which current rootfs is mounted.

  Add '-d' option to return the block device. Otherwise `rootdev` may return
  virtual device like `/dev/dm-0`.

  Returns:
    The rootfs device name, i.e. sda.
  """
  dev_raw = Spawn(['rootdev', '-s', '-d'], read_stdout=True,
                  check_call=True).stdout_data
  return os.path.basename(dev_raw.strip())


def IsDeviceRemovable(dev):
  """Check if device is a removable device.

  Args:
    dev: i.e. sda.
  Returns:
    True if device is removable.
  """
  return file_utils.ReadOneLine(f'/sys/block/{dev}/removable') == '1'


def GetOnboardRootDevice():
  """Get the device name of the on board rootfs.

  Returns:
    The on board rootfs device name, i.e. sda.
  Raises:
    RuntimeError if cannot determine the on board rootfs device.
  """
  devs = [
      dev for dev in ROOT_DEV_NAME_CANDIDATE
      if os.path.isdir(f'/sys/block/{dev}') and not IsDeviceRemovable(dev)
  ]
  if not devs:
    raise RuntimeError(
        'Cannot find on board rootfs device. None of these devices exists and '
        f'is not removable: {ROOT_DEV_NAME_CANDIDATE}')
  if len(devs) > 1:
    raise RuntimeError(
        'Multiple devices are found, cannot determine the on board rootfs '
        f'device: {devs}')
  return devs[0]


def GetDeviceMountPointMapping(dev):
  """Get a mapping of partition -> mount_point.

  Args:
    dev: i.e. sda.
  Returns:
    Partition to mount_point mapping. If the partition is not mounted,
    mount_point is None.
  """
  lines = Spawn(['lsblk', '-nro', 'NAME,MOUNTPOINT', f'/dev/{dev}'],
                read_stdout=True, check_call=True).stdout_data.splitlines()
  res = {}
  for line in lines:
    tokens = line.split()
    if not tokens:
      continue
    res[tokens[0]] = tokens[1] if len(tokens) > 1 else None
  return res


def GetPartitionName(dev, index):
  """Get partition name from device name and index.

  Returns:
    Partition name, add `p` between device name and index if the device is not a
    sata device.
  """
  return f'{dev}{index}' if dev.startswith('sd') else f'{dev}p{index}'


@contextlib.contextmanager
def MountInputDevice(dev):
  """Mount the rootfs on the device and yield the paths.

  Try to mount each partition we need if it is not already mounted.

  According to `src/platform2/init/upstart/test-init/factory_utils.sh`, when
  device is booted with a test image (usually it should be, if the devices have
  run factory toolkit), there are two partitions 1 and 3 which contain the info
  we need.
  `/etc` is under root partition which is partition 3.
  `/usr/local` is bind-mounted to '/mnt/stateful_partition/dev_image' which is
  `dev_image` under partition 1.
  Normally, '/var' is mounted by `mount_encrypted`. However, if factory toolkit
  is enabled, `/var` is bind-mounted to '/mnt/stateful_partition/var' which is
  `var` under partition 1.

  Note that partition 3 (rootfs) is mounted with ext2. Don't use ext4 which may
  modify fs superblock information and making rootfs verification fail.

  Yields:
    A dict of paths indicating where should the log directories be redirected
    to.
  """
  mount_point_map = GetDeviceMountPointMapping(dev)
  with contextlib.ExitStack() as stack:
    mount = {}
    for part_id, fstype in [(1, 'ext4'), (3, 'ext2')]:
      part = GetPartitionName(dev, part_id)
      if mount_point_map[part]:
        mount[part_id] = mount_point_map[part]
      else:
        # If the partition is mounted by us, unmount it at the end.
        unmounter = sys_utils.MountPartition(f'/dev/{part}', fstype=fstype)
        mount[part_id] = stack.enter_context(unmounter)

    yield {
        'var': os.path.join(mount[1], 'var'),
        'usr_local': os.path.join(mount[1], 'dev_image'),
        'etc': os.path.join(mount[3], 'etc'),
    }


@contextlib.contextmanager
def MountRemovable(read_only=False):
  """Mounts (or re-uses) a removable device.

  Scan all the devices under /sys/block/, use the first removable device. Check
  if there is any mounted partition. Yield that partition or try to mount a
  partition of the device.

  Args:
    read_only: If we mount device we mount it read only. Used by goofy_rpc.py

  Yields:
    MountUSBInfo: This is used by goofy_rpc.py

  Raises:
    RuntimeError if no removable device is available or cannot mount any
    partition of a removable device.
  """
  devices = [os.path.basename(x) for x in glob('/sys/block/*')]
  removables = [x for x in devices if IsDeviceRemovable(x)]
  if not removables:
    raise RuntimeError('No removable device is available.')

  if len(removables) > 1:
    logging.warning('More than one removable devices are found: %s', removables)
  dev = removables[0]

  mount_point_map = GetDeviceMountPointMapping(dev)
  for part, mount_point in mount_point_map.items():
    if mount_point:
      logging.info('Using mounted device %s on %s', part, mount_point)
      yield MountUSBInfo(dev=dev, mount_point=mount_point, temporary=False)
      # The device is synced once to make sure the data is written to the device
      # since we cannot guarantee that this device will be unmount correctly.
      Spawn(['sync'], call=True)
      return

  # Try to mount the whole device first, then try to mount each partition.
  partitions = sorted(x for x in mount_point_map)
  for part in partitions:
    try:
      mounter = sys_utils.MountPartition(f'/dev/{part}', rw=not read_only)
    except Exception:
      logging.debug('Mount %s failed.', part)
      continue
    with mounter as mount_point:
      logging.warning('Mount success. Mounted `%s` at `%s`', part, mount_point)
      yield MountUSBInfo(dev=dev, mount_point=mount_point, temporary=True)
      return

  raise RuntimeError(f'Unable to mount any of {partitions}')


def HasEC():
  """SuperIO-based platform has no EC chip, check its existence first.

  Returns:
    True if the platform has EC chip.
  """
  try:
    has_ec = Spawn(['ectool', 'version'], read_stdout=True,
                   ignore_stderr=True).returncode == 0
  except OSError:
    # The system might not have 'ectool' command if the platform has no EC chip.
    has_ec = False
  return has_ec


def AppendLogToABT(abt_file, log_file):
  for f in [abt_file, log_file]:
    if not os.path.isfile(f):
      logging.warning('%s is not a valid file.', f)
      return

  logging.debug('ABT: adding %s.', log_file)

  with open(abt_file, 'ab') as f:
    f.write(b'%s=<multi-line>\n' % log_file.encode('utf-8'))
    f.write(b'---------- START ----------\n')
    f.write(file_utils.ReadFile(log_file, encoding=None))
    f.write(b'---------- END ----------\n')


def GenerateDRAMCalibrationLog(tmp_dir):
  dram_logs = [
      'DRAMK_LOG',          # Plain text logs for devices with huge output in
                            # memory training, for example Kukui.
      'RO_DDR_TRAINING',    # On ARM devices that training data is unlikely to
                            # change and used by both recovery and normal boot,
                            # for example Trogdor.
      'RW_DDR_TRAINING',    # On ARM devices that may retrain due to aging, for
                            # example Kukui.
      'RECOVERY_MRC_CACHE', # On most X86 devices, for recovery boot.
      'RW_MRC_CACHE',       # On most x86 devices, for normal boot.
  ]
  with file_utils.UnopenedTemporaryFile() as bios_bin:
    Spawn(['flashrom', '-p', 'host', '-r', bios_bin],
          check_call=True, ignore_stdout=True, ignore_stderr=True)
    Spawn(['dump_fmap', '-x', bios_bin] + dram_logs,
          check_call=True, ignore_stdout=True, ignore_stderr=True, cwd=tmp_dir)

  # Special case of trimming DRAMK_LOG. DRAMK_LOG is a readable file with some
  # noise appended, like this: TEXT + 0x00 + (0xff)*N
  dramk_file = os.path.join(tmp_dir, 'DRAMK_LOG')
  if os.path.isfile(dramk_file):
    with open(dramk_file, 'rb+') as f:
      data = f.read()
      f.seek(0)
      f.write(data.strip(b'\xff').strip(b'\x00'))
      f.truncate()

  return [log for log in dram_logs
          if os.path.isfile(os.path.join(tmp_dir, log))]


def SaveLogs(output_dir, archive_id=None, net=False, probe=False, dram=False,
             abt=False, var='/var', usr_local='/usr/local', etc='/etc'):
  """Saves dmesg and relevant log files to a new archive in output_dir.

  The archive will be named factory_bug.<description>.zip,
  where description is the 'archive_id' argument (if provided).

  Args:
    output_dir: The directory in which to create the file.
    include_network_log: Whether to include network related logs or not.
    archive_id: An optional short ID to put in the filename (so
      archives may be more easily differentiated).
    probe: True to include probe result in the logs.
    dram: True to include DRAM calibration logs.
    abt: True to include abt.txt for Android Bug Tool.
    var, usr_local, etc: Paths to the relevant directories.

  Returns:
    The name of the zip archive joined with `output_dir`.
  """
  output_dir = os.path.realpath(output_dir)
  files = []

  filename = 'factory_bug.'
  if archive_id:
    filename += archive_id.replace('/', '') + '.'
  filename += 'zip'

  output_file = os.path.join(output_dir, filename)
  if os.path.exists(output_file):
    raise RuntimeError('Same filename [%s] exists. Use `factory_bug --id` or '
                       'add description in goofy UI dialog.' % filename)

  if sys_utils.InChroot():
    # Just save a dummy zip.
    with file_utils.TempDirectory() as d:
      open(os.path.join(os.path.join(d, 'dummy-factory-bug')), 'w').close()
      Spawn(['zip', os.path.join(d, output_file),
             os.path.join(d, 'dummy-factory-bug')], check_call=True)
    return output_file

  with file_utils.TempDirectory(prefix='factory_bug.') as tmp:

    # Create abt.txt to support Android Bug Tool (ABT), which lives in tmp dir
    # but only gets included in bug report when 'abt' is set to True.
    abt_name = 'abt.txt'
    abt_file = os.path.join(tmp, abt_name)
    file_utils.TouchFile(abt_file)

    with open(os.path.join(tmp, 'crossystem'), 'w') as f:
      Spawn('crossystem', stdout=f, stderr=f, check_call=True)
      files += ['crossystem']

    with open(os.path.join(tmp, 'dmesg'), 'w') as f:
      Spawn('dmesg', stdout=f, check_call=True)
      files += ['dmesg']

    with open(os.path.join(tmp, 'mosys_eventlog'), 'w') as f:
      Spawn(['mosys', 'eventlog', 'list'], stdout=f, stderr=f, call=True)
      files += ['mosys_eventlog']

    with open(os.path.join(tmp, 'audio_diagnostics'), 'w') as f:
      Spawn('audio_diagnostics', stdout=f, stderr=f, call=True)
      files += ['audio_diagnostics']

    if HasEC():
      with open(os.path.join(tmp, 'ec_version'), 'w') as f:
        Spawn(['ectool', 'version'], stdout=f, check_call=True)
      files += ['ec_version']
      with open(os.path.join(tmp, 'ec_console'), 'w') as f:
        Spawn(['ectool', 'console'],
              stdout=f, stderr=f, call=True)
      files += ['ec_console']

    # Cannot zip an unseekable file, need to manually copy it instead.
    with open(os.path.join(tmp, 'bios_log'), 'w') as f:
      Spawn(['cat', '/sys/firmware/log'], stdout=f, call=True)
      files += ['bios_log']

    if probe:
      with open(os.path.join(tmp, 'probe_result.json'), 'w') as f:
        Spawn(['hwid', 'probe'], stdout=f, ignore_stderr=True, call=True)
      files += ['probe_result.json']

    files += sum([
        glob(x) for x in [
            os.path.join(var, 'log'),
            os.path.join(var, 'factory'),
            os.path.join(var, 'spool', 'crash'),
            os.path.join(usr_local, 'factory', 'TOOLKIT_VERSION'),
            os.path.join(usr_local, 'factory', 'hwid'),
            os.path.join(etc, 'lsb-release'),
            os.path.join(usr_local, 'etc', 'lsb-*'),
            # These are hardcoded paths because they are virtual
            # filesystems; the data we want is always in /dev and
            # /sys, never on the SSD.
            '/sys/fs/pstore',
        ]], [])

    if abt:
      # Except those debug info that are explicitly created e.g. cros_system,
      # dmesg etc., the following files are also valuable.
      files_for_abt = sum([
          glob(x) for x in [
              os.path.join(var, 'factory', 'log', '*.log'),
              os.path.join(var, 'log', 'messages'),
              os.path.join(var, 'log', 'power_manager', 'powerd.LATEST'),
              os.path.join('/sys/fs/pstore', 'console-ramoops-0'),
          ]], [])

      for path in files + files_for_abt:
        path = os.path.join(tmp, path)
        if os.path.isfile(path):
          # Considering a file is informational for preliminary diagnosis if
          # it's explicitly included in `files`. Directories and its underlying
          # files are ignored.
          # If you know other informational files in some directories,
          # enumerate them in `files_for_abt`.
          AppendLogToABT(abt_file, path)

      # Finally, include abt.txt in the archive.
      files += [abt_name]

    # Generate DRAM logs after adding files into abt.txt, since some of them
    # are unreadable and we don't want them to be included.
    if dram:
      files += GenerateDRAMCalibrationLog(tmp)
      # Manually add trimmed DRAMK_LOG into abt file
      if 'DRAMK_LOG' in files and abt:
        AppendLogToABT(abt_file, os.path.join(tmp, 'DRAMK_LOG'))

    # Name of Chrome data directory within the state directory.
    chrome_data_dir_name = 'chrome-data-dir'

    # Exclude various items from bug reports.
    exclude_files = list(
        chain.from_iterable(('--exclude', x) for x in [
            os.path.join(env_paths.DATA_STATE_DIR, chrome_data_dir_name),
            os.path.join(var, 'log', 'journal/*'),
            'Extensions',
        ]))
    if not net:
      exclude_files += ['--exclude', os.path.join(var, 'log', 'net.log')]

    file_utils.TryMakeDirs(os.path.dirname(output_file))
    logging.info('Saving %s to %s...', files, output_file)
    compress_method = ['zip', output_file]
    process = Spawn(compress_method + exclude_files + ['-r'] + files,
                    cwd=tmp, call=True,
                    ignore_stdout=True,
                    read_stderr=True)
    # 0 = successful termination
    # 1 = non-fatal errors like "some files differ"
    if process.returncode not in [0, 1]:
      logging.error('zip stderr:\n%s', process.stderr_data)
      raise IOError('zip process failed with returncode %d' %
                    process.returncode)

    logging.info('Wrote %s (%d bytes)', output_file,
                 os.path.getsize(output_file))

  return output_file


def ParseArgument():
  """argparse config

  Returns:
    (parser, args)
    parser: the argparse.ArgumentParser object, export for `parser.error()`.
    args: parsed command line arguments.
  """
  parser = argparse.ArgumentParser(
      description=DESCRIPTION, epilog=EXAMPLES,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument(
      '--output-dir', '-o', metavar='DIR',
      help=('Output directory in which to save file. Normally default to '
            f'`/tmp`, but defaults to `{USB_ROOT_OUTPUT_DIR}` when booted '
            'from USB.'))
  parser.add_argument(
      '--save-to-removable', '-s', action='store_true',
      help=('Save logs to a USB stick. (Using any mounted USB drive partition '
            'if available, otherwise attempting to temporarily mount one)'))
  parser.add_argument(
      '--input-device', '-d', metavar='DEV',
      help=('Collect logs from the specific device. Input device is detected '
            'automatically if omitted.'))
  parser.add_argument(
      '--net', action='store_true',
      help=('Whether to include network related logs or not. Network logs are '
            'excluded by default.'))
  parser.add_argument(
      '--id', '-i', metavar='ID',
      help=('Short ID to include in file name to help differentiate archives.'))
  parser.add_argument('--probe', action='store_true',
                      help=('Include probe result in the logs.'))
  parser.add_argument('--dram', action='store_true',
                      help=('Include DRAM calibration info in the logs.'))
  parser.add_argument('--no-abt', action='store_false', dest='abt',
                      help=('Create abt.txt for "Android Bug Tool".'))
  parser.add_argument(
      '--full', action='store_true',
      help=('Produce a complete factory_bug. When --full is set --net, --probe'
            ' and --dram are implied. For details see the description of each '
            'option.'))
  parser.add_argument('--verbosity', '-v', action='count', default=0,
                      help=('Change the logging verbosity.'))
  return parser, parser.parse_args()


def IsBlockDevice(dev_path):
  return os.path.exists(dev_path) and stat.S_ISBLK(os.stat(dev_path).st_mode)


@contextlib.contextmanager
def InputDevice(root_is_removable, input_device):
  """Get input paths. See `MountInputDevice`."""
  if input_device:
    if not IsBlockDevice(input_device):
      logging.error('"%s" is not a block device.', input_device)
      sys.exit(1)
  elif root_is_removable:
    input_device = GetOnboardRootDevice()
    logging.info('Root is removable. Try to collect logs from "%s"',
                 input_device)
  else:
    yield {}
    return
  with MountInputDevice(input_device) as paths:
    yield paths


@contextlib.contextmanager
def OutputDevice(root_is_removable, save_to_removable, output_dir, parser):
  """Get output path."""
  if save_to_removable:
    if root_is_removable:
      parser.error(
          '--save-to-removable only applies when root device is not removable.')
    with MountRemovable() as mount:
      yield mount.mount_point
    return

  if not output_dir:
    output_dir = USB_ROOT_OUTPUT_DIR if root_is_removable else '/tmp'
  yield output_dir


def main():
  parser, args = ParseArgument()
  logging.basicConfig(level=logging.WARNING - 10 * args.verbosity)
  options = dict((key, getattr(args, key) or args.full)
                 for key in ['net', 'probe', 'dram'])
  root_is_removable = IsDeviceRemovable(GetRootDevice())

  input_device = InputDevice(root_is_removable, args.input_device)
  output_device = OutputDevice(root_is_removable, args.save_to_removable,
                               args.output_dir, parser)
  with input_device as input_paths, output_device as output_path:
    SaveLogs(output_path, args.id, **options, **input_paths)


if __name__ == '__main__':
  main()
