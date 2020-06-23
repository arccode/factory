# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A system module providing access to permanent storage on device."""

import json
import logging
import re
import subprocess

from cros.factory.device import device_types
from cros.factory.utils import process_utils


class Storage(device_types.DeviceComponent):
  """Persistent storage on device."""

  _DICT_FILENAME = 'STORAGE_SAVED_DICT.json'

  def GetFactoryRoot(self):
    """Returns the directory for factory environment (code and resources)."""
    return '/usr/local/factory'

  def GetDataRoot(self):
    """Returns the directory for persistent data."""
    return '/var/factory'

  def GetDictFilePath(self):
    """Returns the path to saved key-value pairs file on device."""
    return self._device.path.join(self.GetDataRoot(), self._DICT_FILENAME)

  def LoadDict(self):
    """Returns a dictionary of key-value pairs stored in device."""
    data = {}
    if self._device.path.exists(self.GetDictFilePath()):
      try:
        data = json.loads(self._device.ReadFile(self.GetDictFilePath()))
      except ValueError:
        logging.exception('Failed to load key-value pairs from %s',
                          self.GetDictFilePath())
        data = {}
      if not isinstance(data, dict):
        logging.warning('%r is not a dict object, will reset to {}', data)
        data = {}
    else:
      logging.info('Cannot find %s, will create new dict object',
                   self.GetDictFilePath())
    return data

  def SaveDict(self, data):
    """Replaces key-value pairs stored on device.

    All existing key-value pairs will be deleted and replaced by `data`.
    Keys must be strings and values must be JSON serializable.
    All non-string keys will be removed before stringify key-value pairs.

    Args:
      data: a dict, new key-value pairs.
    """
    assert isinstance(data, dict), '%r is not a dict object' % data

    invalid_keys = [k for k in data if not isinstance(k, str)]
    if invalid_keys:
      logging.warning('Invalid keys: %r (keys can only be string)',
                      invalid_keys)
      logging.warning('These keys will be removed')
      data = {k: v for (k, v) in data.items() if k not in invalid_keys}

    device_data_file_path = self.GetDictFilePath()

    self._device.CheckCall(
        ['mkdir', '-p', self._device.path.dirname(device_data_file_path)])
    # TODO(stimim): we might need to lock the file while writing.
    self._device.WriteFile(
        self.GetDictFilePath(), json.dumps(data, sort_keys=True))
    self._device.Call(['sync'])
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
    filesystems = self._device.toybox.df(path)
    if not filesystems:
      logging.warning('cannot find mount point of %s', path)
      return None, None
    return filesystems[0].mounted_on, filesystems[0].filesystem

  def GetMountPoint(self, path):
    """Returns a pair (mount_point, device) where path is mounted.

    Since _GetMountPointByDiskFree will fail if path doesn't exist. We will drop
    each component in the path until new path exists. Then use
    _GetMountPointByDiskFree to get the mount point and device of new path.
    """
    while not self._device.path.exists(path):
      new_path = self._device.path.dirname(path)
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
    if self._device.Call(cmd) != 0:
      logging.error('remount: Cannot remount mount point: %s', mount_point)
      return False

    return True

  def _GetMainStorageDeviceMountPoint(self):
    """Path that is used to find main storage device."""
    return '/usr/local'

  def GetMainStorageDevice(self):
    main_storage_device_mount_point = self._GetMainStorageDeviceMountPoint()
    partition = self.GetMountPoint(main_storage_device_mount_point)[1]
    if not partition:
      raise IOError('Unable to find main storage device (%s)' %
                    main_storage_device_mount_point)
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

  def Remount(self, path, options='rw'):
    mount_point, _ = self.GetMountPoint(path)

    # 'mount -o remount' may fail on Android. The standard way is adb remount
    # for '/system', '/vendor' to get read / write permission.
    if options == 'rw':
      if mount_point == '/data':
        # /data is default rw, return directly.
        return True
      if mount_point in ['/system', '/vendor', '/oem']:
        try:
          process_utils.CheckOutput(['adb', 'remount'])
          return True
        except subprocess.CalledProcessError:
          logging.error('remount: failed to run adb remount.')
          return False
    return super(AndroidStorage, self).Remount(path, options)
