# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to retrieve system information and status."""

from __future__ import print_function

import glob
import logging
import os
import re
import subprocess

import factory_common  # pylint: disable=W0611
from cros.factory import hwid
from cros.factory.system import partitions
from cros.factory import test
from cros.factory.test import dut
from cros.factory.test import factory
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils.sys_utils import MountDeviceAndReadFile


class SystemInfo(object):
  """Static information about the system.

  This is mostly static information that changes rarely if ever
  (e.g., version numbers, serial numbers, etc.).
  """
  # If not None, an update that is available from the update server.
  update_md5sum = None

  # The cached release image version and channel.
  release_image_version = None
  release_image_channel = None
  allowed_release_channels = ['dev', 'beta', 'stable']

  def __init__(self, dut_instance=None):
    self.dut = dut.Create() if dut_instance is None else dut_instance

    self.mlb_serial_number = None
    try:
      self.mlb_serial_number = test.shopfloor.GetDeviceData()[
          'mlb_serial_number']
    except:
      pass

    self.serial_number = None
    try:
      self.serial_number = test.shopfloor.get_serial_number()
      if self.serial_number is not None:
        self.serial_number = str(self.serial_number)
    except:
      pass

    self.stage = None
    try:
      self.stage = test.shopfloor.GetDeviceData()['stage']
    except:
      pass

    self.factory_image_version = None
    try:
      lsb_release = open('/etc/lsb-release').read()
      match = re.search('^GOOGLE_RELEASE=(.+)$', lsb_release,
                        re.MULTILINE)
      if match:
        self.factory_image_version = match.group(1)
    except:
      pass

    self.toolkit_version = None
    try:
      with open('/usr/local/factory/TOOLKIT_VERSION') as f:
        self.toolkit_version = f.read().strip()
    except:
      pass

    def _GetReleaseLSBValue(lsb_key):
      """Gets the value from the lsb-release file on release image."""
      if not _GetReleaseLSBValue.lsb_content:
        try:
          release_rootfs = partitions.RELEASE_ROOTFS.path
          _GetReleaseLSBValue.lsb_content = (
              MountDeviceAndReadFile(release_rootfs, '/etc/lsb-release'))
        except:
          pass

      match = re.search('^%s=(.+)$' % lsb_key,
                        _GetReleaseLSBValue.lsb_content,
                        re.MULTILINE)
      if match:
        return match.group(1)
      else:
        return None
    # The cached content of lsb-release file.
    _GetReleaseLSBValue.lsb_content = ""

    self.release_image_version = None
    if SystemInfo.release_image_version:
      self.release_image_version = SystemInfo.release_image_version
      logging.debug('Obtained release image version from SystemInfo: %r',
                    self.release_image_version)
    else:
      logging.debug('Release image version does not exist in SystemInfo. '
                    'Try to get it from lsb-release from release partition.')

      self.release_image_version = _GetReleaseLSBValue('GOOGLE_RELEASE')
      if self.release_image_version:
        logging.debug('Release image version: %s', self.release_image_version)
        logging.debug('Cache release image version to SystemInfo.')
        SystemInfo.release_image_version = self.release_image_version
      else:
        logging.debug('Can not read release image version from lsb-release.')

    self.release_image_channel = None
    if SystemInfo.release_image_channel:
      self.release_image_channel = SystemInfo.release_image_channel
      logging.debug('Obtained release image channel from SystemInfo: %r',
                    self.release_image_channel)
    else:
      logging.debug('Release image channel does not exist in SystemInfo. '
                    'Try to get it from lsb-release from release partition.')

      self.release_image_channel = _GetReleaseLSBValue('CHROMEOS_RELEASE_TRACK')
      if self.release_image_channel:
        logging.debug('Release image channel: %s', self.release_image_channel)
        logging.debug('Cache release image channel to SystemInfo.')
        SystemInfo.release_image_channel = self.release_image_channel
      else:
        logging.debug('Can not read release image channel from lsb-release.')

    self.wlan0_mac = None
    try:
      for wlan_interface in ['mlan0', 'wlan0']:
        address_path = os.path.join('/sys/class/net/',
                                    wlan_interface, 'address')
        if os.path.exists(address_path):
          self.wlan0_mac = open(address_path).read().strip()
    except:
      pass

    self.eth_macs = dict()
    try:
      eth_paths = glob.glob('/sys/class/net/eth*')
      for eth_path in eth_paths:
        address_path = os.path.join(eth_path, 'address')
        if os.path.exists(address_path):
          self.eth_macs[os.path.basename(eth_path)] = open(
              address_path).read().strip()
    except:
      self.eth_macs = None

    self.kernel_version = None
    try:
      uname = subprocess.Popen(['uname', '-r'], stdout=subprocess.PIPE)
      stdout, _ = uname.communicate()
      self.kernel_version = stdout.strip()
    except:
      pass

    self.architecture = None
    try:
      self.architecture = Spawn(['uname', '-m'],
                                check_output=True).stdout_data.strip()
    except:
      pass

    self.ec_version = None
    try:
      self.ec_version = self.dut.ec.GetECVersion()
    except:
      pass

    self.pd_version = None
    try:
      self.pd_version = self.dut.ec.GetPDVersion()
    except:
      pass

    self.firmware_version = None
    try:
      crossystem = subprocess.Popen(['crossystem', 'fwid'],
                                    stdout=subprocess.PIPE)
      stdout, _ = crossystem.communicate()
      self.firmware_version = stdout.strip() or None
    except:
      pass

    self.mainfw_type = None
    try:
      crossystem = subprocess.Popen(['crossystem', 'mainfw_type'],
                                    stdout=subprocess.PIPE)
      stdout, _ = crossystem.communicate()
      self.mainfw_type = stdout.strip() or None
    except:
      pass

    self.root_device = None
    try:
      rootdev = Spawn(['rootdev', '-s'],
                      stdout=subprocess.PIPE, ignore_stderr=True)
      stdout, _ = rootdev.communicate()
      self.root_device = stdout.strip()
    except:
      pass

    self.factory_md5sum = factory.get_current_md5sum()

    # Uses checksum of hwid file as hwid database version.
    self.hwid_database_version = None
    try:
      hwid_file_path = os.path.join(hwid.common.DEFAULT_HWID_DATA_PATH,
                                    hwid.common.ProbeBoard().upper())
      if os.path.exists(hwid_file_path):
        self.hwid_database_version = hwid.hwid_utils.ComputeDatabaseChecksum(
            hwid_file_path)
    except:
      pass

    # update_md5sum is currently in SystemInfo's __dict__ but not this
    # object's.  Copy it from SystemInfo into this object's __dict__.
    self.update_md5sum = SystemInfo.update_md5sum


if __name__ == '__main__':
  import yaml
  print(yaml.dump(SystemInfo(None, None).__dict__, default_flow_style=False))
