#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A system module providing access to permanent storage on DUT"""

import json
import logging
import re

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component


class Storage(component.DUTComponent):
  """Persistent storage on DUT."""

  _DICT_FILENAME = 'DUT_SAVED_DICT.json'

  def GetFactoryRoot(self):
    """Returns the directory for factory environment (code and resources)."""
    return '/usr/local/factory'

  def GetDataRoot(self):
    """Returns the directory for persistent data."""
    return '/var/factory'

  def GetDictFilePath(self):
    """Returns the path to saved key-value pairs file on DUT."""
    return self._dut.path.join(self.GetDataRoot(), self._DICT_FILENAME)

  def LoadDict(self):
    """Returns a dictionary of key-value pairs stored in DUT."""
    data = {}
    if self._dut.path.exists(self.GetDictFilePath()):
      try:
        data = json.loads(self._dut.ReadFile(self.GetDictFilePath()))
      except ValueError:
        logging.exception('Failed to load key-value pairs from %s',
                          self.GetDictFilePath())
        data = {}
      if not isinstance(data, dict):
        logging.warn('%r is not a dict object, will reset to {}', data)
        data = {}
    else:
      logging.info('Cannot find %s, will create new dict object',
                   self.GetDictFilePath())
    return data

  def SaveDict(self, data):
    """Replaces key-value pairs stored on DUT.

    All existing key-value pairs will be deleted and replaced by `data`.
    Keys must be strings and values must be JSON serializable.
    All non-string keys will be removed before stringify key-value pairs.

    Args:
      data: a dict, new key-value pairs.
    """
    assert isinstance(data, dict), '%r is not a dict object' % data

    invalid_keys = [k for k in data if not isinstance(k, basestring)]
    if invalid_keys:
      logging.warn('Invalid keys: %r (keys can only be string)', invalid_keys)
      logging.warn('These keys will be removed')
      data = {k: v for (k, v) in data.iteritems() if k not in invalid_keys}

    device_data_file_path = self.GetDictFilePath()

    self._dut.CheckCall(['mkdir', '-p',
                         self._dut.path.dirname(device_data_file_path)])
    # TODO(stimim): we might need to lock the file while writing.
    self._dut.WriteFile(self.GetDictFilePath(),
                        json.dumps(data, sort_keys=True))
    return data

  def UpdateDict(self, E, **F):
    """Partially updates some key-value pairs stored in DUT.

    If E present and has a .keys() method, does::

      for k in E: data[k] = E[k]

    If E present and lacks .keys() method, does::

      for (k, v) in E: data[k] = v

    In either case, this is followed by::

      for k in F: data[k] = F[k]
    """
    data = self.LoadDict()
    data.update(E, **F)
    return self.SaveDict(data)

  def DeleteDict(self, key):
    """Remove key `key` from key-value pairs stored in DUT.

    If `key` is in device data, the key-value pair of `key` will be removed.
    Otherwise, does nothing.
    """
    data = self.LoadDict()
    if key in data:
      data.pop(key)
      self.SaveDict(data)
    return data

  def _GetMountPointByDiskFree(self, path):
    """Returns a pair (mount_point, device) where path is mounted.

    Unlike GetMountPoint, path is directly passed to df even if it doesn't
    exist.
    """
    filesystems = self._dut.toybox.df(path)
    if not filesystems:
      logging.warn('cannot find mount point of %s', path)
      return None, None
    else:
      return filesystems[0].mounted_on, filesystems[0].filesystem

  def GetMountPoint(self, path):
    """Returns a pair (mount_point, device) where path is mounted.

    Since _GetMountPointByDiskFree will fail if path doesn't exist. We will drop
    each component in the path until new path exists. Then use
    _GetMountPointByDiskFree to get the mount point and device of new path.
    """
    while not self._dut.path.exists(path):
      new_path = self._dut.path.dirname(path)
      if new_path == path:
        break
      path = new_path

    return self._GetMountPointByDiskFree(path)

  def Remount(self, path, options='rw'):
    """Remount the file system of path with given options.

    Finds the mount point of file system which the given path belongs to, and
    then remount the file system with specified options.
    Useful for changing file system into write-able state, or to allow file
    execution.

    Args:
      path: A string for the path to re-mount.
      options: A string for the option to remount (passed to mount(1),
               defaults to 'rw').
    """
    mount_point, _ = self.GetMountPoint(path)
    if not mount_point:
      logging.error('remount: Cannot get mount point of %s', path)
      return False

    cmd = ['mount', '-o', 'remount,%s' % options, mount_point]
    if self._dut.Call(cmd) != 0:
      logging.error('remount: Cannot remount mount point: %s', mount_point)
      return False

    return True

  def _GetMainStorageDeviceMountPoint(self):
    """Path that is used to find main storage device."""
    return '/usr/local'

  def GetMainStorageDevice(self):
    partition = self.GetMountPoint(self._GetMainStorageDeviceMountPoint())[1]
    if not partition:
      raise IOError('Unable to find main storage device (%s)',
                    self._MAIN_STORAGE_DEVICE_MOUNT_POINT)
    # remove partition suffix to get device path.
    return re.sub(r'p?(\d+)$', '', partition)


class AndroidStorage(Storage):
  """Persistent storage on Android.

  On Android, partitions that have rw default enabled include /data and
  /sdcard, but not every Android devices have /sdcard. On the oher
  hand, most Android devices put tmp files in /data/local/tmp, so here we
  choose /data/local/factory as the location to store persist factory data.
  /data/local/factory/source is used for factory software, and
  /data/local/factory/data is used for persist factory data.
  """

  def GetFactoryRoot(self):
    return '/data/local/factory/source'

  def GetDataRoot(self):
    return '/data/local/factory/data'

  def _GetMainStorageDeviceMountPoint(self):
    return '/data'
