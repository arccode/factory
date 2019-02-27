# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility for updating software components from Chrome OS factory server.

This module provides helper functions to reach factory server, check and perform
updates if available.

To check if update to component 'hwid' is available::

  updater = update_utils.Updater(updat_utils.COMPONENTS.hwid)
  print('Remote version: %s' % updater.GetUpdateVersion())
  if updater.IsUpdateAvailable(current_version):
    print('Update found!')

To download the 'toolkit' component (which is a self-extracted installer) and
then execute::

  with file_utils.UnopenedTemporaryFile() as f:
    updater = update_utils.Updater(update_utils.COMPONENTS.toolkit)
    updater.PerformUpdate(destination=f)
    os.system(f)

To directly install 'release_image' (block device component)::

  updater = update_utils.Updater(update_utils.COMPONENTS.release_image)
  updater.PerformUpdate(destination='/dev/mmcblk0')
"""

import json
import logging
import urllib2

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import server_proxy
from cros.factory.umpire.client import umpire_client
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils


# A list of known components.
COMPONENTS = type_utils.Enum([
    'hwid', 'toolkit', 'release_image', 'firmware', 'netboot_firmware'])
MATCH_METHOD = type_utils.Enum(['exact', 'substring'])


class Updater(object):
  """A helper to update software components from factory server."""

  KEY_VERSION = 'version'

  def __init__(self, component, proxy=None, spawn=None):
    self._component = component
    self._url = None
    self._payload = {}
    self._proxy = proxy
    self._loaded = False
    self._spawn = spawn or (
        lambda command: process_utils.Spawn(command, log=True, check_call=True))

  def GetUpdateInfo(self, force_reload=False):
    """Gets raw information of updates on server."""
    if self._loaded and not force_reload:
      return self._payload

    # GetServerProxy() may hang for few seconds so we don't want to do it in
    # __init__. Also, _proxy may be a proxy object that will forward __nonzero__
    # to remote so we should check if it's None explicitly.
    proxy = self._proxy
    if proxy is None:
      proxy = server_proxy.GetServerProxy()
    payloads = {}
    dut_info = umpire_client.UmpireClientInfo().GetDUTInfoComponents()
    url = proxy.GetCROSPayloadURL(dut_info['x_umpire_dut'])
    if url:
      payloads = json.loads(urllib2.urlopen(url).read())
    self._url = url
    self._payload = payloads.get(self._component, {})
    self._loaded = True
    return self._payload

  def GetUpdateVersion(self, key=None):
    """Returns the version of available update."""
    if key is None:
      key = self.KEY_VERSION
    info = self.GetUpdateInfo()
    return info.get(key)

  def IsUpdateAvailable(self, current_version=None,
                        match_method=MATCH_METHOD.exact):
    """Checks if updates to component are available.

    Args:
      current_version: identifier of local version to compare with remote
          payload.
      match_method: method of identifing the current_version and update_version.

    Returns:
      True if remote updates are available, otherwise False.
    """
    update_version = self.GetUpdateVersion()
    if not update_version:
      return False
    if match_method == MATCH_METHOD.exact:
      return current_version != update_version
    else:
      return current_version not in update_version

  def UpdateCallback(self, component, destination, url):
    """A callback function after an update is installed.

    Args:
      component: a string for the type of component.
      destination: where the update was installed, usually block device or
          directory.
      url: a string for the URL to original payload JSON config.
    """
    logging.info('Successfully updated %s in %s from %s.', component,
                 destination, url)

  def PerformUpdate(self, destination=None, callback=None,):
    """Updates a component by remote payload.

    Args:
      destination: a string to block device or directory for where to install
         the update, or None to create a temporary folder.
      callback: a callable function after installation, defaults to
         Updater.UpdateCallback.
    """
    if destination is None:
      with file_utils.TempDirectory() as tmp_dir:
        return self.PerformUpdate(destination=tmp_dir, callback=callback)

    # Ensure the component information is already fetched.
    self.GetUpdateInfo()
    self._spawn(
        ['cros_payload', 'install', self._url, destination, self._component])
    if not callback:
      callback = self.UpdateCallback
    return callback(self._component, destination, self._url)


def UpdateHWIDDatabase(dut=None, target_dir=None):
  """Updates HWID database file on a DUT.

  Args:
    dut: A reference to the device under test.
        :rtype: cros.factory.device.types.DeviceBoard

  Returns:
    True if new database is applied.
  """
  updater = Updater(COMPONENTS.hwid)
  if dut is None:
    dut = device_utils.CreateDUTInterface()
  else:
    dut.info.Invalidate('hwid_database_version')

  current_version = dut.info.hwid_database_version
  # TODO(hungte) Currently dut.info.hwid_database_version does not support
  # remote DUT so we have to always download if DUT is on remote. We can remove
  # this hack when dut.info.hwid_database_version supports remote DUT.
  if not dut.link.IsLocal():
    current_version = None
    if target_dir is None:
      # Only set target_dir for remote DUT since we will need to invoke mkdir.
      target_dir = '/usr/local/factory/hwid'

  update_version = updater.GetUpdateVersion()
  if not update_version or current_version in update_version.splitlines():
    return False

  with file_utils.UnopenedTemporaryFile() as local_path:
    with dut.temp.TempFile() as remote_path:
      updater.PerformUpdate(destination=local_path)
      dut.SendFile(local_path, remote_path)
      command = ['sh', remote_path]
      if target_dir:
        # Remote may not have target_dir so we have to create it first.
        dut.CheckCall(['mkdir', '-p', target_dir])
        command += [target_dir]
      dut.CheckCall(command)

  # TODO(hungte) Send event to Goofy that info is changed.
  dut.info.Invalidate('hwid_database_version')
  return True
