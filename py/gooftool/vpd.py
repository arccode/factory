# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re
import subprocess

from cros.factory.gooftool import common as gooftool_common


# ChromeOS firmware VPD partition names.
VPD_READONLY_PARTITION_NAME = 'RO_VPD'
VPD_READWRITE_PARTITION_NAME = 'RW_VPD'


class VPDTool:
  """This class wraps the functions supplied by VPD cmdline tool into methods.
  """
  _KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_.]+$')

  def __init__(self, shell=None, raw_file=None):
    self._shell = shell or gooftool_common.Shell
    self._raw_file = raw_file

  def GetValue(self, key, default_value=None, partition=None, filename=None):
    """Gets a VPD value with the specific key.

    If the VPD doesn't contain the data with the given `key`, this function will
    return `default_value`.

    Args:
      key: A string of the key of the data to get.
      default_value: The value to return if the data doesn't exist.
      filename: Filename of the bios image, see `vpd -h` for detail.
      partition: Specify VPD partition name in fmap.

    Returns:
      A string of raw value data or `None`.
    """
    self._EnsureIfKeyValid(key)
    try:
      return self._InvokeCmd(
          self._BuildBasicCmd(partition, filename) + ['-g', key])
    except subprocess.CalledProcessError:
      if filename is not None:
        self._CheckFileExistence(filename)
      return default_value

  def GetAllData(self, partition=None, filename=None):
    """Gets all VPD data in dictionary format.

    Args:
      filename: Filename of the bios image, see `vpd -h` for detail.
      partition: Specify VPD partition name in fmap.

    Returns:
      A dictionary in which each key-value pair represents a VPD data entry.
    """
    raw_data = self._InvokeCmd(
        self._BuildBasicCmd(partition, filename) + ['-l', '--null-terminated'])
    result = dict(field.split('=', 1) for field in raw_data.split('\0')
                  if '=' in field)
    if not result and filename is not None:
      self._CheckFileExistence(filename)
    return result

  def UpdateData(self, items, partition=None, filename=None):
    """Updates VPD data.

    Args:
      items: Items to set.  A value of "None" deletes the item from the VPD.
      filename: Filename of the bios, see `vpd -h` for detail.
      partition: Specify VPD partition name in fmap.
    """
    cmd = self._BuildBasicCmd(partition, filename)
    for k, v in items.items():
      self._EnsureIfKeyValid(k)
      cmd += ['-d', k] if v is None else ['-s', '%s=%s' % (k, v)]
    self._InvokeCmd(cmd)
    self._UpdateCache()

  def _CheckFileExistence(self, filename):
    # This could be CheckCall. However, to reduce API dependency, we are
    # reusing CheckOutput.
    self._InvokeCmd(['test', '-e', filename])

  def _InvokeCmd(self, cmd):
    proc_result = self._shell(cmd)
    if not proc_result.success:
      raise subprocess.CalledProcessError(proc_result.status, cmd)
    return proc_result.stdout

  def _BuildBasicCmd(self, partition, filename):
    cmd = ['vpd']
    if partition:
      cmd += ['-i', partition]
    if filename:
      cmd += ['-f', filename]
    elif self._raw_file:
      cmd += ['--raw', '-f', self._raw_file]
    return cmd

  def _UpdateCache(self):
    """Updates VPD cache file."""
    self._InvokeCmd(['dump_vpd_log', '--force'])

  @classmethod
  def _EnsureIfKeyValid(cls, key):
    if not cls._KEY_PATTERN.match(key):
      raise ValueError('Invalid VPD key %r (does not match pattern %s)' %
                       (key, cls._KEY_PATTERN.pattern))
