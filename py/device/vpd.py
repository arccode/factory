# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import functools
import logging

import factory_common  # pylint: disable=unused-import
from cros.factory.device import types
from cros.factory.test.rules import privacy
from cros.factory.gooftool import common as gooftool_common
from cros.factory.gooftool import vpd


class Partition(types.DeviceComponent):
  """A VPD partition.

  This should not be created by the caller; rather, the caller should use
  vpd.ro or vpd.rw."""

  def get(self, key, default=None):
    """Returns a single item from the VPD, or default if not present.

    This invokes the 'vpd' command each time it is run; for efficiency,
    use GetAll if more than one value is desired.
    """
    raise NotImplementedError

  def Delete(self, *keys):
    """Deletes entries from the VPD.

    Raises:
      An error if any entries cannot be deleted.  In this case some or
      all other entries may have been deleted.
    """
    raise NotImplementedError


  def GetAll(self):
    """Returns the contents of the VPD as a dict."""
    raise NotImplementedError

  def Update(self, items, log=True):
    """Updates items in the VPD.

    Args:
      items: Items to set.  A value of "None" deletes the item.
      log: Whether to log the action.  Keys in VPD_BLACKLIST_KEYS are replaced
        with a redacted value.
    """
    raise NotImplementedError


class CommandVPDPartition(Partition):
  """A VPD partition that is accessed by command 'vpd'.

  The 'vpd' command is usually available on systems using ChromeOS firmware that
  internally calls flashrom to read and set VPD data in firmware SPI flash.
  """

  def __init__(self, dut, name):
    """Constructor.

    Args:
      name: The name of the partition (e.g., 'RO_VPD').
    """
    super(CommandVPDPartition, self).__init__(dut)
    self.name = name
    shell_func = functools.partial(gooftool_common.Shell, sys_interface=dut)
    self._vpd_tool = vpd.VPDTool(shell_func)

  def get(self, key, default=None):
    """See Partition.get."""
    return self._vpd_tool.GetValue(
        key, default_value=default, partition=self.name)

  def Delete(self, *keys):
    """See Partition.Delete."""
    self._vpd_tool.UpdateData({key: None for key in keys}, partition=self.name)

  def GetAll(self):
    """See Partition.GetAll."""
    return self._vpd_tool.GetAllData(partition=self.name)

  def Update(self, items, log=True):
    """See Partition.Update.

    Args:
      items: Items to set.  A value of "None" deletes the item
        from the VPD (actually, it currently just sets the field to empty:
        http://crosbug.com/p/18159).
    """
    if log:
      logging.info('Updating %s: %s', self.name, privacy.FilterDict(items))

    # Only update if needed since reading is fast but writing is slow.
    orig_data = self._vpd_tool.GetAllData(partition=self.name)
    changed_items = {}
    for k, v in items.items():
      if (v is None and k in orig_data or
          v is not None and orig_data.get(k) != v):
        changed_items[k] = v

    return self._vpd_tool.UpdateData(changed_items, partition=self.name)


class ImmutableFileBasedPartition(Partition):
  """A file-based VPD partition which cannot be updated."""

  def __init__(self, device, path):
    """Constructor.

    Args:
      device: Instance of cros.factory.device.types.DeviceInterface.
      path: The path of the partition (e.g., '/persist', '/sys/firmware/vpd').
    """
    super(ImmutableFileBasedPartition, self).__init__(device)
    self._path = path

  def get(self, key, default=None):
    """See Partition.get"""
    file_path = self._device.path.join(self._path, key)
    if self._device.path.exists(file_path):
      return self._device.ReadFile(file_path)
    return None

  def Delete(self, *keys):
    """See Partition.Delete. This operation is not supported."""
    raise NotImplementedError('An immutable partition cannot be updated.')

  def GetAll(self):
    """See Partition.GetAll."""
    ret = {}
    for file_name in self._device.CheckOutput(
        ['find', self._path, '-type', 'f']).splitlines():
      name = file_name[len(self._path) + 1:]
      ret[name] = self._device.ReadFile(file_name)
    return ret

  def Update(self, items, log=True):
    """See Partition.Update. This operation is not supported."""
    raise NotImplementedError('An immutable partition cannot be updated.')


class MutableFileBasedPartition(ImmutableFileBasedPartition):
  """A file-based VPD partition."""

  def Delete(self, *keys):
    """See Partition.Delete."""
    for key in keys:
      file_path = self._device.path.join(self._path, key)
      if self._device.path.exists(file_path):
        self._device.CheckCall(['rm', '-f', file_path])
        return

  def Update(self, items, log=True):
    """See Partition.Update."""
    for k, v in items.items():
      file_name = self._device.path.join(self._path, k)
      if v is not None:
        dir_name = self._device.path.dirname(file_name)
        self._device.CheckCall(['mkdir', '-p', dir_name])
        self._device.WriteFile(file_name, v)
      else:
        self._device.CheckCall(['rm', '-f', file_name])
    # Make sure files are synced to the disk.
    self._device.CheckCall(['sync'])


class VPDSource(types.DeviceComponent):
  """A source to read Vital Product Data (VPD).

  Properties:
    ro: Access to Read-Only partition.
    rw: Access to Read-Write partition.
  """

  @types.DeviceProperty
  def ro(self):
    raise NotImplementedError

  @types.DeviceProperty
  def rw(self):
    raise NotImplementedError

  def GetPartition(self, partition):
    if partition == 'rw':
      return self.rw
    elif partition == 'ro':
      return self.ro
    raise types.DeviceException('No %s partition found.' % partition)


class CommandVPDSource(VPDSource):
  """A source to read VPD from command 'vpd'."""

  @types.DeviceProperty
  def ro(self):
    return CommandVPDPartition(self._device, vpd.VPD_READONLY_PARTITION_NAME)

  @types.DeviceProperty
  def rw(self):
    return CommandVPDPartition(self._device, vpd.VPD_READWRITE_PARTITION_NAME)


class FileBasedVPDSource(VPDSource):
  """A source to read VPD from files."""

  def __init__(self, dut, path):
    super(FileBasedVPDSource, self).__init__(dut)
    self._path = path
    self._partition = MutableFileBasedPartition(self._device, self._path)

  @types.DeviceProperty
  def ro(self):
    return self._partition

  @types.DeviceProperty
  def rw(self):
    return self._partition


class SysFSVPDSource(VPDSource):
  """A source to read VPD from sysfs."""

  def __init__(self, dut, path=None):
    super(SysFSVPDSource, self).__init__(dut)
    if path is None:
      path = '/sys/firmware/vpd'
    self._path = path

  @types.DeviceProperty
  def ro(self):
    return ImmutableFileBasedPartition(
        self._device,
        self._device.path.join(self._path, 'ro'))

  @types.DeviceProperty
  def rw(self):
    return ImmutableFileBasedPartition(
        self._device,
        self._device.path.join(self._path, 'rw'))


class VitalProductData(types.DeviceComponent):
  """System module for Vital Product Data (VPD)."""

  @types.DeviceProperty
  def live(self):
    """An VPD source to read live VPD values."""
    raise NotImplementedError

  @types.DeviceProperty
  def boot(self):
    """An VPD source to read VPD values cached at boot time."""
    raise NotImplementedError

  @types.DeviceProperty
  def ro(self):
    """A shortcut to read ro from live VPD source."""
    return self.live.ro

  @types.DeviceProperty
  def rw(self):
    """A shortcut to read rw from live VPD source."""
    return self.live.rw

  def GetPartition(self, partition):
    """A shortcut to get partition from live VPD source."""
    return self.live.GetPartition(partition)


class ChromeOSVitalProductData(VitalProductData):
  """System module for Vital Product Data (VPD) on Chrome OS."""

  def __init__(self, dut, path=None):
    super(ChromeOSVitalProductData, self).__init__(dut)
    self._sysfs_path = path
    if self._sysfs_path is None:
      self._sysfs_path = '/sys/firmware/vpd'

  @types.DeviceProperty
  def live(self):
    return CommandVPDSource(self._device)

  @types.DeviceProperty
  def boot(self):
    return SysFSVPDSource(self._device, self._sysfs_path)


class AndroidVitalProductData(VitalProductData):
  """System module for Vital Product Data (VPD) on Andoird OS."""

  def __init__(self, dut, path=None):
    super(AndroidVitalProductData, self).__init__(dut)
    self._path = path
    if self._path is None:
      self._path = '/persist'

  @types.DeviceProperty
  def boot(self):
    raise NotImplementedError

  @types.DeviceProperty
  def live(self):
    return FileBasedVPDSource(self._device, self._path)
