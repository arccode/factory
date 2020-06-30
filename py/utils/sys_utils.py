# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A collective of system-related functions."""

from contextlib import contextmanager
import logging
import os
import re
import stat
import tempfile

from . import file_utils
from . import process_utils
from . import pygpt
from . import sync_utils
from . import type_utils


class MountPartitionException(Exception):
  """Exception for MountPartition."""


def MountPartition(source_path, index=None, mount_point=None, rw=False,
                   options=None, fstype=None, dut=None):
  """Mounts a partition in an image or a block device.

  Args:
    source_path: The image file or a block device.
    index: The index of the partition, or None to mount as a single
      partition. If source_path is a block device, index must be None.
    mount_point: The mount point.  If None, a temporary directory is used.
    rw: Whether to mount as read/write.
    options: A list of options to add to the -o argument when mounting, e.g.,
        ['offset=8192', 'sizelimit=1048576'].
    fstype: A string to specify file system type.
    dut: a cros.factory.device.device_types.DeviceInterface instance, None for
      local.

  Raises:
    OSError: if image file or mount point doesn't exist.
    subprocess.CalledProcessError: if mount fails.
    MountPartitionException: if index is given while source_path is a block
      device.
  """
  local_mode = dut is None
  path = os.path if local_mode else dut.path

  if not path.exists(source_path):
    raise OSError('Image file %s does not exist' % source_path)

  all_options = ['rw' if rw else 'ro']
  # source_path is a block device.
  if local_mode:
    is_blk = stat.S_ISBLK(os.stat(source_path).st_mode)
  else:
    is_blk = dut.CheckOutput(
        ['stat', '-c', '%F', source_path]) == 'block special file'

  if is_blk:
    if index:
      raise MountPartitionException('index must be None for a block device.')
  else:
    # Use loop option on image file.
    all_options.append('loop')

  if index:
    partitions = PartitionManager(source_path, dut)
    sector_size = partitions.GetSectorSize()
    offset = sector_size * partitions.GetPartitionOffsetInSector(index)
    all_options.append('offset=%d' % offset)
    sizelimit = sector_size * partitions.GetPartitionSizeInSector(index)
    all_options.append('sizelimit=%d' % sizelimit)

  if options:
    all_options.extend(options)

  if not mount_point:
    # Put this after all other options, so that no temp directory would be left
    # if any above raised exception.
    if local_mode:
      mount_point = tempfile.mkdtemp(prefix='mount_partition.')
    else:
      mount_point = dut.temp.mktemp(is_dir=True, prefix='mount_partition.')

    remove_mount_point = True
  else:
    remove_mount_point = False

  if not path.isdir(mount_point):
    raise OSError('Mount point %s does not exist' % mount_point)

  for line in file_utils.ReadLines('/proc/mounts', dut):
    if line.split()[1] == mount_point:
      raise OSError('Mount point %s is already mounted' % mount_point)

  command = ['toybox'] if (not local_mode and
                           dut.Call(['type', 'toybox']) == 0) else []
  command += ['mount', '-o', ','.join(all_options)]
  if fstype is not None:
    command += ['-t', fstype]
  command += [source_path, mount_point]

  try:
    if local_mode:
      process_utils.Spawn(command, log=True, check_call=True, sudo=True)
    else:
      dut.CheckCall(command, log=True)
  except Exception:
    # Remove temporary directory if mount fail.
    if remove_mount_point:
      if local_mode:
        try:
          os.rmdir(mount_point)
        except OSError:
          pass
      else:
        dut.Call(['rm', '-rf', mount_point])
    raise

  @contextmanager
  def Unmounter():
    try:
      yield mount_point
    finally:
      logging.info('Unmounting %s', mount_point)

      if local_mode:
        umount = lambda: process_utils.Spawn(
            ['umount', mount_point], call=True,
            sudo=True, ignore_stderr=True).returncode == 0
      else:
        umount = lambda: dut.Call(['umount', mount_point]) == 0

      if not sync_utils.Retry(5, 1, None, umount):
        logging.warning('Unable to umount %s', mount_point)

      if remove_mount_point:
        if local_mode:
          try:
            os.rmdir(mount_point)
          except OSError:
            pass
        else:
          dut.Call(['rm', '-rf', mount_point])

  return Unmounter()


def MountDeviceAndReadFile(device, path, dut=None):
  """Mounts a device and reads a file on it.

  Args:
    device: The device like '/dev/mmcblk0p5'.
    path: The file path like '/etc/lsb-release'. The file to read is then
      'mount_point/etc/lsb-release'.
    dut: a cros.factory.device.device_types.DeviceInterface instance, None for
      local.

  Returns:
    The content of the file.

  Raises:
    Exception if mount or umount fails.
    IOError if the file can not be read.
  """
  # Remove the starting / of the path.
  path = re.sub('^/', '', path)
  with MountPartition(device, dut=dut) as mount_point:
    logging.debug('Mounted at %s.', mount_point)
    if dut is None:
      content = open(
          os.path.join(mount_point, path)).read()
    else:
      content = dut.ReadSpecialFile(dut.path.join(mount_point, path))
  return content


def LoadKernelModule(name, error_on_fail=True):
  """Ensures kernel module is loaded.  If not already loaded, do the load."""
  loaded = process_utils.Spawn('lsmod | grep -q %s' % name,
                               call=True, shell=True).returncode == 0
  if not loaded:
    loaded = process_utils.Spawn('modprobe %s' % name,
                                 call=True, shell=True).returncode == 0
    if not loaded and error_on_fail:
      raise OSError('Cannot load kernel module: %s' % name)
  return loaded


def GetInterrupts():
  """Gets the list of interrupt names and its count.

  Returns:
    A dict of interrupt names to their interrupt counts.  The interrupt names
    are all strings even if some of the names are numbers, e.g. the name for
    interrupt 88 is "88" instead of 88.
  """
  interrupt_count = {}

  lines = file_utils.ReadLines('/proc/interrupts')
  if not lines:
    raise OSError('Unable to read /proc/interrupts')

  # First line indicates CPUs in system
  num_cpus = len(lines.pop(0).split())

  for line_num, line in enumerate(lines, start=1):
    fields = line.split()
    if len(fields) < num_cpus + 1:
      logging.error('Parse error at line %d: %s', line_num, line)
      continue
    interrupt = fields[0].strip().split(':')[0]
    count = sum(map(int, fields[1:1 + num_cpus]))
    interrupt_count[interrupt] = count
    logging.debug('interrupt[%s] = %d', interrupt, count)

  return interrupt_count


def GetI2CBus(device_names):
  """Lookup I2C Bus by device name(s).

  Args:
    device_names: List of allowed device name.
                  (Ex: we can list second-source components here)

  Returns:
    I2C bus index. None if not found
  """
  blankline = re.compile(r'\n\n', flags=re.MULTILINE)
  blocks = blankline.split(file_utils.ReadFile('/proc/bus/input/devices'))
  matched_blocks = [b for b in blocks if any(d in b for d in device_names)]
  if not matched_blocks:
    logging.error('GetI2CBus(%r): Device is not found', device_names)
    return None
  if len(matched_blocks) > 1:
    logging.error('GetI2CBus(%r): Multiple devices are found', device_names)
    return None
  found = re.search(r'^S: *Sysfs=.*/i2c-([0-9]+)/', matched_blocks[0],
                    flags=re.MULTILINE)
  if not found:
    logging.error('GetI2CBus(%r): Invalid format', device_names)
    return None
  return int(found.group(1))


class PartitionInfo:
  """A class that holds the info of a partition."""

  def __init__(self, major, minor, blocks, name):
    self.major = major
    self.minor = minor
    self.blocks = blocks
    self.name = name

  def __str__(self):
    return ('%5s %5s %10s %-20s' %
            (self.major, self.minor, self.blocks, self.name))


def GetPartitions():
  """Gets a list of partition info.

  Example content of /proc/partitions:

    major minor  #blocks  name

       8        0  976762584 sda
       8        1     248832 sda1
       8        2          1 sda2
       8        5  976510976 sda5
       8       16  175825944 sdb
       8       17  175825943 sdb1
     252        0   39059456 dm-0
     252        1  870367232 dm-1
     252        2   67031040 dm-2

  Returns:
    A list of PartitionInfo objects parsed from /proc/partitions.
  """
  line_format = re.compile(
      r'^\s*(\d+)'  # major
      r'\s*(\d+)'   # minor
      r'\s*(\d+)'   # number of blocks
      r'\s*(\w+)$'  # name
  )
  results = []
  lines = file_utils.ReadLines('/proc/partitions')
  for line in lines:
    match_obj = line_format.match(line)
    if match_obj:
      results.append(PartitionInfo(*match_obj.groups()))
  return results


class _GPTTool:
  """Abstraction for tool to manipulate GUID Partition Table."""

  def GetPartitionOffsetInSector(self, index):
    """Returns the partition offset in sectors."""
    raise NotImplementedError

  def GetPartitionSizeInSector(self, index):
    """Returns the partition size in sectors."""
    raise NotImplementedError

  def GetSectorSize(self):
    """Returns logical sector size in bytes."""
    raise NotImplementedError

  def GetTypeGUID(self, index):
    """Returns the type GUID string."""
    raise NotImplementedError

  def IsChromeOsKernelPartition(self, index):
    """Check if the partition is a Chrome OS kernel partition."""
    return self.GetTypeGUID(index) == 'FE3A2A5D-4F32-41A7-B725-ACCC3285A309'

  def IsChromeOsRootFsPartition(self, index):
    """Check if the partition is a Chrome OS rootfs partition."""
    return self.GetTypeGUID(index) == '3CB8E202-3B7E-47DD-8A3C-7FF2A13CFCEC'

  def GetAttribute(self, index):
    """Returns the Attribute value."""
    raise NotImplementedError

  @staticmethod
  def ExtractBits(value, shift, mask):
    return (value >> shift) & mask

  def GetAttributeSuccess(self, index):
    """Returns the Success attribute."""
    return self.ExtractBits(self.GetAttribute(index), 56, 1)

  def GetAttributeTries(self, index):
    """Returns the Tries attribute."""
    return self.ExtractBits(self.GetAttribute(index), 52, 0xf)

  def GetAttributePriority(self, index):
    """Returns the Priority attribute."""
    return self.ExtractBits(self.GetAttribute(index), 48, 0xf)


class PartitionManager(_GPTTool):
  """Provides disk partition information.

  Implemented as a wrapper for commands (pygpt, cgpt, partx) to access disk
  partition.
  """

  @type_utils.Overrides
  def GetPartitionOffsetInSector(self, index):
    """Returns the partition offset in sectors."""
    return self._runner.GetPartitionOffsetInSector(index)

  @type_utils.Overrides
  def GetPartitionSizeInSector(self, index):
    """Returns the partition size in sectors."""
    return self._runner.GetPartitionSizeInSector(index)

  @type_utils.Overrides
  def GetSectorSize(self):
    """Returns logical sector size in bytes."""
    return self._runner.GetSectorSize()

  @type_utils.Overrides
  def GetTypeGUID(self, index):
    """Returns the type GUID string """
    return self._runner.GetTypeGUID(index)

  @type_utils.Overrides
  def GetAttribute(self, index):
    """Returns the Attribute value."""
    return self._runner.GetAttribute(index)

  class _PyGPT(_GPTTool):
    """Manipulate GPT using cros.factory.utils.pygpt."""

    def __init__(self, image_path):
      self._gpt = pygpt.GPT.LoadFromFile(image_path)

    @type_utils.Overrides
    def GetPartitionOffsetInSector(self, index):
      """Returns the partition offset in sectors."""
      return self._gpt.GetPartition(index).FirstLBA

    @type_utils.Overrides
    def GetPartitionSizeInSector(self, index):
      """Returns the partition size in sectors."""
      return self._gpt.GetPartition(index).blocks

    @type_utils.Overrides
    def GetSectorSize(self):
      """Returns logical sector size in bytes."""
      return self._gpt.block_size

    @type_utils.Overrides
    def GetTypeGUID(self, index):
      """Returns the type GUID string."""
      return str(self._gpt.GetPartition(index).TypeGUID).upper()

    @type_utils.Overrides
    def GetAttribute(self, index):
      """Returns the Attribute value."""
      return self._gpt.GetPartition(index).Attributes.raw

  class _CGPT(_GPTTool):
    """Wrapper for cgpt."""

    def __init__(self, cgpt, check_output, path):
      self.cgpt = cgpt
      self.check_output = check_output
      self.path = path

    @type_utils.Overrides
    def GetPartitionOffsetInSector(self, index):
      return int(self.check_output(
          [self.cgpt, 'show', '-i', str(index), '-b', self.path]))

    @type_utils.Overrides
    def GetPartitionSizeInSector(self, index):
      return int(self.check_output(
          [self.cgpt, 'show', '-i', str(index), '-s', self.path]))

    @type_utils.Overrides
    def GetSectorSize(self):
      # Currently cgpt always assumes sector size = 512.
      return 512

    @type_utils.Overrides
    def GetTypeGUID(self, index):
      s = str(self.check_output(
          [self.cgpt, 'show', '-i', str(index), '-t', self.path]))
      return s.strip().upper()

    @type_utils.Overrides
    def GetAttribute(self, index):
      s = str(self.check_output([self.cgpt, 'show', '-i', str(index), '-A',
                                 self.path]))
      v = int(s.strip(), 0)
      v = v << 48  # The returned value is only the bits 48-63
      return v

  class _PartX(_GPTTool):
    """Wrapper for partx."""

    def __init__(self, partx, check_output, path):
      self.partx = partx
      self.check_output = check_output
      self.path = path

    @type_utils.Overrides
    def GetPartitionOffsetInSector(self, index):
      return int(self.check_output([self.partx, '-r', '-g', '-n', str(index),
                                    '-o', 'START', self.path]))

    @type_utils.Overrides
    def GetPartitionSizeInSector(self, index):
      return int(self.check_output([self.partx, '-r', '-g', '-n', str(index),
                                    '-o', 'SECTORS', self.path]))

    @type_utils.Overrides
    def GetSectorSize(self):
      # Currently partx always assumes sector size is 512.
      return 512

    @type_utils.Overrides
    def GetTypeGUID(self, index):
      return str(self.check_output([self.partx, '-r', '-g', '-n', str(index),
                                    '-o', 'TYPE', self.path])).strip().upper()

    @type_utils.Overrides
    def GetAttribute(self, index):
      s = self.check_output([self.partx, '-r', '-g', '-n', str(index),
                             '-o', 'FLAGS', self.path])
      return int(s.strip(), 0)

  def __init__(self, path, dut=None):
    """Constructor of PartitionManager.

    Args:
      path: a path to Deivce which the PartitionManager query on.
      dut: a cros.factory.device.device_types.DeviceInterface instance, None for
        local.

    Raises:
      Exception: If cannot find either cgpt or partx in remote system PATH.
    """
    self._path = path
    local_mode = dut is None or dut.link.IsLocal()
    self._check_output = (process_utils.CheckOutput if local_mode
                          else dut.CheckOutput)
    # Always use pygpt on local since it has less dependency and best speed.
    # For remote, use cgpt over partx since it's more compliant for ChromeOS.
    if local_mode:
      self._runner = PartitionManager._PyGPT(self._path)
    elif dut.Call(['which', 'cgpt']) == 0:
      self._runner = PartitionManager._CGPT(
          'cgpt', self._check_output, self._path)
    elif dut.Call(['which', 'partx']) == 0:
      self._runner = PartitionManager._PartX(
          'partx', self._check_output, self._path)
    else:
      raise Exception('Cannot find cgpt or partx on remote DUT.')


def ResetCommitTime():
  """Remounts partitions with commit=0.

  The standard value on CrOS (commit=600) is likely to result in
  corruption during factory testing.  Using commit=0 reverts to the
  default value (generally 5 s).
  """
  if InChroot():
    return

  devices = set()
  with open('/proc/mounts', 'r') as f:
    for line in f.readlines():
      cols = line.split(' ')
      device = cols[0]
      options = cols[3]
      if 'commit=' in options:
        devices.add(device)

  # Remount all devices in parallel, and wait.  Ignore errors.
  for process in [
      process_utils.Spawn(['mount', p, '-o', 'commit=0,remount'], log=True)
      for p in sorted(devices)]:
    process.wait()


def InChroot():
  """Returns True if currently in the chroot."""
  return 'CROS_WORKON_SRCROOT' in os.environ


def IsContainerized():
  """Returns True if currently in a container.

  Based on how Moby probes container environment but with some revision:
  https://github.com/moby/moby/blob/b248de7e332b6e67b08a8981f68060e6ae629ccf/pkg/parsers/operatingsystem/operatingsystem_linux.go

  Returns:
    A bool.
  """
  try:
    lines = file_utils.ReadFile('/proc/1/cgroup').splitlines()
  except Exception:
    logging.debug('Probably not inside Docker.')
    return False
  return any(
      line and line.split(':', 2)[2] not in ['/', '/init.scope']
      for line in lines)


def GetRunningFactoryPythonArchivePath():
  """Returns path to the python archive that is running, or None.

  If factory toolkit is currently run with a python archive, this function will
  return path to the python archive, otherwise, return None.

  Returns:
    str or None
  """
  # If we are running a python archive, __file__ will be a pseudo path like
  # '/path/to/factory.par/cros/factory/utils/sys_utils.py'

  if os.path.exists(__file__):  # this script is a real file
    return None

  # file doesn't exist, check if a python archive is running
  par_end_idx = __file__.find('/cros/factory/utils/')
  if par_end_idx < 0:
    logging.warning('cannot determine the path of python archive.')
    return None

  factory_par = os.path.realpath(__file__[:par_end_idx])
  if not os.path.exists(factory_par):
    logging.warning('file %s doesn\'t exist', factory_par)
    return None

  return factory_par


def InFactoryPythonArchive():
  """Returns True if factory toolkit is run with a python archive."""
  return GetRunningFactoryPythonArchivePath() is not None


def InQEMU():
  """Returns True if running within QEMU."""
  return 'QEMU' in open('/proc/cpuinfo').read()


def InCrOSDevice():
  """Returns True if running on a Chrome OS device."""
  if not os.path.exists('/etc/lsb-release'):
    return False
  with open('/etc/lsb-release') as f:
    lsb_release = f.read()
  return re.match(r'^CHROMEOS_RELEASE', lsb_release, re.MULTILINE) is not None


def GetVarLogMessages(max_length=256 * 1024,
                      path='/var/log/messages',
                      dut=None):
  """Returns the last n bytes of /var/log/messages.

  Args:
    max_length: Maximum characters of messages.
    path: path to /var/log/messages.
    dut: a cros.factory.device.device_types.DeviceInterface instance, None for
      local.
  """
  return file_utils.TailFile(path, max_length, dut)


def GetVarLogMessagesBeforeReboot(lines=100,
                                  max_length=5 * 1024 * 1024,
                                  path='/var/log/messages',
                                  dut=None):
  """Returns the last few lines in /var/log/messages before the current boot.

  Args:
    lines: number of lines to return.
    max_length: maximum amount of data at end of file to read.
    path: path to /var/log/messages.
    dut: a cros.factory.device.device_types.DeviceInterface instance, None for
      local.

  Returns:
    The last few lines in /var/log/messages before the current boot.
    Empty if the marker indicating kernel boot could not be found.
  """

  data = file_utils.TailFile(path, max_length, dut)

  # Find the last element matching the RE signaling kernel start.
  matches = list(re.finditer(
      r'^(\S+)\s.*kernel:\s+\[\s+0\.\d+\] Linux version', data, re.MULTILINE))
  if not matches:
    return ''

  match = matches[-1]
  tail_lines = data[:match.start()].split('\n')
  tail_lines.pop()  # Remove incomplete line at end

  # Skip some common lines that may have been written before the Linux
  # version.
  while tail_lines and any(
      re.search(x, tail_lines[-1])
      for x in [r'0\.000000\]',
                r'rsyslogd.+\(re\)start',
                r'/proc/kmsg started']):
    tail_lines.pop()

  # Done! Return the last few lines.
  output = tail_lines[-lines:] + [
      '<after reboot, kernel came up at %s>' % match.group(1)]
  return '\n'.join(output) + '\n'
