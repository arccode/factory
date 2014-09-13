# -*- coding: utf-8 -*-
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Module for umpire client update utilities."""


import collections
import logging
import gzip
import StringIO
import urllib2

from cros.factory.umpire.client import umpire_client


UpdateInfo = collections.namedtuple('UpdateInfo',
                                    ['needs_update', 'md5sum', 'url', 'scheme'])
"""Information about update of a component.

Properties:
  needs_update: True if an update is needed, False otherwise.
  md5sum: The new md5sum of component on the server.
  update_url: The url of component on the server.
    Note that for device factory toolkit this is the root directory
    of device, so the factory directory is <update_url>/usr/local/factory/.
  scheme: update scheme provided by Umpire server, e.g. 'http', 'rsync'.
"""

class UmpireClientGetUpdateException(Exception):
  """Exception for Umpire client get_update utils."""
  pass


def GetUpdateForComponents(proxy, components):
  """Gets update information of components from Umpire server.

  Args:
    proxy: An UmpireServerProxy that connects to Umpire server.
    components: A list of component names. They must be in
      umpire_client.COMPONENT_KEYS.

  Returns:
    A dict containing mapping from component name to UpdateInfo.

  Raises:
    UmpireClientGetUpdateException: If components contains invalid keys.
  """
  invalid_keys = set(components) - umpire_client.COMPONENT_KEYS
  if invalid_keys:
    raise UmpireClientGetUpdateException(
        'Invalid keys in components: %r' % invalid_keys)
  update_dict = proxy.GetUpdate(
      umpire_client.UmpireClientInfo().GetDUTInfoComponents())
  logging.info('update_dict: %r', update_dict)
  ret = dict([key,
              UpdateInfo(needs_update=update_dict[key]['needs_update'],
                         md5sum=update_dict[key]['md5sum'],
                         url=update_dict[key]['url'],
                         scheme=update_dict[key]['scheme'])]
             for key in components)
  return ret


def NeedImageUpdate(proxy):
  """Checks if device need to update test or release image.

  Args:
    proxy: An UmpireServerProxy that connects to Umpire server.

  Returns:
    True if device needs to update image.
  """
  update_info = GetUpdateForComponents(proxy, ['rootfs_test', 'rootfs_release'])
  logging.info('Update info for image: %r', update_info)
  return (update_info['rootfs_test'].needs_update or
          update_info['rootfs_release'].needs_update)


def GetUpdateForDeviceFactoryToolkit(proxy):
  """Gets update information for device factory toolkit.

  Args:
    proxy: An UmpireServerProxy that connects to Umpire server.

  Returns:
    A UpdateInfo for device factory toolkit.
  """
  return GetUpdateForComponents(
      proxy, ['device_factory_toolkit'])['device_factory_toolkit']


def GetUpdateForHWID(proxy):
  """Gets HWID update from Umpire server.

  The user of this method is get_hwid_updater in cros.factory.test.shopfloor.
  For backward compatibility, this method returns the content of HWID shell
  ball file to hide the difference between GetHWIDUpdater XMLRPC call in
  shopfloor v1, v2 and GetUpdate mechanism in Umpire.

  Args:
    proxy: An UmpireServerProxy that connects to Umpire server.

  Returns:
    None if there is no HWID update. Otherwise, return unzipped HWID update
    bundle file content.
  """
  update_info = GetUpdateForComponents(
      proxy, ['hwid'])['hwid']
  if not update_info.needs_update:
    return None
  if update_info.scheme != 'http':
    raise UmpireClientGetUpdateException('HWID update scheme %s other than http'
        ' is not supported.' % update_info.scheme)
  return DownloadAndUnzip(update_info.url)


def DownloadAndUnzip(url):
  """Downloads a gzip file and returns its unzipped content.

  Args:
    url: The url of the gzip file.

  Returns:
    The unzipped content.
  """
  gz_file_content = urllib2.urlopen(url).read()
  string_io = StringIO.StringIO(gz_file_content)
  content = None
  with gzip.GzipFile(fileobj=string_io) as f:
    content = f.read()
  return content


def GetUpdateForFirmware(proxy):
  """Gets firmware update from Umpire server.

  The user of this method is get_firmware_updater in cros.factory.test.shopfloor.
  This method returns the content of unzipped firmware.gz file, that is,
  chromeos-firmwareupdate.

  Args:
    proxy: An UmpireServerProxy that connects to Umpire server.

  Returns:
    None if there is no firmware update. Otherwise, return unzipped
    chromeos-firmwareupdate file content.
  """
  update_info_firmware = GetUpdateForComponents(
      proxy, ['firmware_ec', 'firmware_bios'])
  logging.info('Update info for firmware: %r', update_info_firmware)

  if (update_info_firmware['firmware_ec'].needs_update or
      update_info_firmware['firmware_bios'].needs_update):
    logging.info('Need firmware update from Umpire')
  else:
    return None

  if (update_info_firmware['firmware_ec'].md5sum !=
      update_info_firmware['firmware_bios'].md5sum):
    raise UmpireClientGetUpdateException(
        'Md5sum for ec and bios firmware updater are different: %s != %s',
        update_info_firmware['firmware_ec'].md5sum,
        update_info_firmware['firmware_bios'].md5sum)

  update_info = update_info_firmware['firmware_ec']

  if update_info.scheme != 'http':
    raise UmpireClientGetUpdateException(
        ('Firmware update scheme %s other than http is not supported.'
         % update_info.scheme))
  return DownloadAndUnzip(update_info.url)
