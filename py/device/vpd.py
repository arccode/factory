#!/usr/bin/python
# pylint: disable=W0212
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import re

import factory_common  # pylint: disable=W0611
from cros.factory.device import component
from cros.factory.test.rules import privacy


# One line in vpd -l output.
VPD_LIST_PATTERN = re.compile(r'^"([^"]+)"="([^"]*)"$')

# Allowable VPD keys: alphanumeric and _ and .
VPD_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_.]+')

# Allowable VPD values: all printable ASCII characters except for
# double-quote.
VPD_VALUE_PATTERN = re.compile(r'^[ !#-~]*$')

# ChromeOS firmware VPD partition names.
VPD_READONLY_PARTITION_NAME = 'RO_VPD'
VPD_READWRITE_PARTITION_NAME = 'RW_VPD'


class Partition(component.DeviceComponent):
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


class ChromeOSPartition(Partition):
  """A VPD partition that can be accessed by command 'vpd'.

  The 'vpd' command is usually available on systems using ChromeOS firmware that
  internally calls flashrom to read and set VPD data in firmware SPI flash.
  """

  def __init__(self, dut, name):
    """Constructor.

    Args:
      name: The name of the partition (e.g., 'RO_VPD').
    """
    super(ChromeOSPartition, self).__init__(dut)
    self.name = name

  def get(self, key, default=None):
    """See Partition.get."""
    result = self._dut.CallOutput(['vpd', '-i', self.name, '-g', key])
    return default if result is None else result

  def Delete(self, *keys):
    """See Partition.Delete."""
    if keys:
      args = ['vpd', '-i', self.name]
      for k in keys:
        args += ['-d', k]
      self._dut.CheckCall(args)

  def GetAll(self):
    """See Partition.GetAll."""
    ret = {}
    for line in self._dut.CallOutput(
        ['vpd', '-i', self.name, '-l']).splitlines():
      match = VPD_LIST_PATTERN.match(line)
      if not match:
        logging.error('Unexpected line in %s VPD: %r', self.name, line)
        continue
      ret[match.group(1)] = match.group(2)

    return ret

  def Update(self, items, log=True):
    """See Partition.Update.

    Args:
      items: Items to set.  A value of "None" deletes the item
        from the VPD (actually, it currently just sets the field to empty:
        http://crosbug.com/p/18159).
    """
    if log:
      logging.info('Updating %s: %s', self.name, privacy.FilterDict(items))

    data = self.GetAll()
    command = ['vpd', '-i', self.name]

    for k, v in sorted(items.items()):
      if not VPD_KEY_PATTERN.match(k):
        raise ValueError('Invalid VPD key %r (does not match pattern %s)' % (
            k, VPD_KEY_PATTERN.pattern))
      if v is None:
        v = ''  # TODO(jsalz): http://crosbug.com/p/18159
      if not VPD_VALUE_PATTERN.match(v):
        raise ValueError('Invalid VPD value %r (does not match pattern %s)' % (
            k, VPD_VALUE_PATTERN.pattern))
      # Only update if needed since reading is fast but writing is slow.
      if data.get(k) != v:
        command += ['-s', '%s=%s' % (k, v)]

    if not items:
      return

    self._dut.CheckCall(command)


class FileBasedPartition(Partition):
  """A file-based VPD partition."""

  def __init__(self, dut, path):
    """Constructor.

    Args:
      dut: Instance of cros.factory.device.board.DeviceBoard.
      path: The path of the partition (e.g., '/persist').
    """
    super(FileBasedPartition, self).__init__(dut)
    self._path = path

  def get(self, key, default=None):
    """See Partition.get"""
    file_path = self._dut.path.join(self._path, key)
    if self._dut.path.exists(file_path):
      return self._dut.ReadFile(file_path)
    return None

  def Delete(self, *keys):
    """See Partition.Delete."""
    for key in keys:
      file_path = self._dut.path.join(self._path, key)
      if self._dut.path.exists(file_path):
        return self._dut.CheckCall(['rm', '-f', file_path])

  def GetAll(self):
    """See Partition.GetAll."""
    ret = {}
    for file_name in self._dut.CheckOutput(
        ['find', self._path, '-type', 'f']).splitlines():
      name = file_name[len(self._path) + 1:]
      ret[name] = self._dut.ReadFile(file_name)
    return ret

  def Update(self, items, log=True):
    """See Partition.Update."""
    for k, v in items.items():
      file_name = self._dut.path.join(self._path, k)
      if v is not None:
        dir_name = self._dut.path.dirname(file_name)
        self._dut.CheckCall(['mkdir', '-p', dir_name])
        self._dut.WriteFile(file_name, v)
      else:
        self._dut.CheckCall(['rm', '-f', file_name])
    # Make sure files are synced to the disk.
    self._dut.CheckCall(['sync'])


class VitalProductData(component.DeviceComponent):
  """System module for Vital Product Data (VPD).

  Properties:
    ro: Access to Read-Only partition.
    rw: Access to Read-Write partition.
  """

  @component.DeviceProperty
  def ro(self):
    raise NotImplementedError

  @component.DeviceProperty
  def rw(self):
    raise NotImplementedError

  def GetPartition(self, partition):
    if partition == 'rw':
      return self.rw
    elif partition == 'ro':
      return self.ro
    raise component.DeviceException('No %s partition found.' % partition)


class ChromeOSVitalProductData(VitalProductData):
  """System module for Vital Product Data (VPD) on Chrome OS."""

  @component.DeviceProperty
  def ro(self):
    return ChromeOSPartition(self._dut, VPD_READONLY_PARTITION_NAME)

  @component.DeviceProperty
  def rw(self):
    return ChromeOSPartition(self._dut, VPD_READWRITE_PARTITION_NAME)


class FileBasedVitalProductData(VitalProductData):
  """System module for file-based Vital Product Data."""

  def __init__(self, dut, path):
    super(FileBasedVitalProductData, self).__init__(dut)
    self._path = path
    self._partition = FileBasedPartition(self._dut, self._path)

  @component.DeviceProperty
  def ro(self):
    return self._partition

  @component.DeviceProperty
  def rw(self):
    return self._partition
