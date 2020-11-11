# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""A plugin that is used to setup station information."""

import logging
import os
import re
import subprocess

from cros.factory.goofy.plugins import plugin
from cros.factory.test.env import paths
from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test.test_lists import test_list
from cros.factory.tools.goofy_ghost import ghost_prop
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils


_DEFAULT_STATION_KEYS = [('station_name', _('Station Name')),
                         ('line_number', _('Manufacture Line Number')),
                         ('station_number', _('Station Number'))]

_OVL_BIN = os.path.join(paths.FACTORY_DIR, 'bin', 'ovl')
_OVERLORD_DEFAULT_PORT = 9000


class StationSetup(plugin.Plugin):
  """A Goofy plugin that is used to setup a station."""

  def __init__(self, goofy, key_desc=None, check_overlord=True,
               overlord_login=None, overlord_port=_OVERLORD_DEFAULT_PORT):
    """Initialize the plugin.

    Args:
      key_desc: A list of tuples (key to check, description of the key).
          default to _DEFAULT_STATION_KEYS.
      check_overlord: Whether to check duplicate on Overlord. If set to True,
          would use the keys in key_desc to determine duplicate. Can also be
          set to a non-empty list of keys to determine duplicate.
      overlord_login: The username and password for HTTP basic auth to overlord
          server, in the form of (username, password).
      overlord_port: The port that ovl should be connecting to.
    """
    super(StationSetup, self).__init__(goofy)

    self.key_desc = key_desc
    self.check_overlord = check_overlord
    # TODO(pihsun): Do we need a less privileged account for overlord_login?
    self.overlord_login = overlord_login
    self.overlord_port = overlord_port

    if self.key_desc is None:
      self.key_desc = _DEFAULT_STATION_KEYS
    for idx, (key, description) in enumerate(self.key_desc):
      self.key_desc[idx] = (key, test_list.MayTranslate(description))

    self.key_desc_dict = dict(self.key_desc)

    if self.check_overlord is True:
      self.check_overlord = [key for key, unused_description in self.key_desc]

  def _GetOverlordAddress(self):
    """Get the connected overlord address from running ghost client."""
    try:
      status = process_utils.CheckOutput(['ghost', '--status'])
      logging.info('ghost status: %s', status)
    except subprocess.CalledProcessError:
      return None
    if status.startswith('success '):
      ip, unused_port = status.split(' ', 1)[1].split(':')
      return (ip, self.overlord_port)
    return None

  def _OvlConnect(self):
    address = self._GetOverlordAddress()
    if address is None:
      return False

    # TODO(pihsun): Make this work when server TLS is enabled.
    connect_cmd = [_OVL_BIN, 'connect']

    if self.overlord_login is not None:
      # pylint: disable=unpacking-non-sequence
      username, password = self.overlord_login
      connect_cmd.extend(['-u', username, '-w', password])

    ip, port = address  # pylint: disable=unpacking-non-sequence
    connect_cmd.extend([ip, str(port)])

    output = process_utils.CheckOutput(connect_cmd, log=True)
    # TODO(pihsun): Make ovl return non-zero when connection fail, so this
    # check is not needed.
    if not re.match(r'connection to .* established.', output):
      return False
    return True

  def _CheckOverlordForDuplicate(self, properties):
    if not self.check_overlord:
      return False

    check_dict = {key: properties[key] for key in self.check_overlord}

    if not self._OvlConnect():
      logging.warning("Can't connect to overlord server, skipping check.")
      return False

    ls_cmd = [_OVL_BIN, 'ls', '--mid-only']
    for key, value in check_dict.items():
      ls_cmd.extend(['-f', '%s=^%s$' % (key, re.escape(value))])
    match_clients = process_utils.CheckOutput(ls_cmd, log=True).splitlines()

    # Filter self out.
    my_device_id = session.GetDeviceID()
    match_clients = [mid for mid in match_clients if mid != my_device_id]
    if match_clients:
      logging.info('duplicate clients: %r', match_clients)

    return bool(match_clients)

  def ShowUpdateDialog(self):
    return plugin.MenuItem.ReturnData(
        action=plugin.MenuItem.Action.RUN_AS_JS,
        data='this.showStationSetupDialog();')

  @type_utils.Overrides
  def GetUILocation(self):
    return 'testlist'

  @type_utils.Overrides
  def GetMenuItems(self):
    # TODO(pihsun): Make the order of menu items stable across plugins.
    # Currently the order differs for each factory_restart.
    return [plugin.MenuItem(text=_('Update Station Properties'),
                            callback=self.ShowUpdateDialog,
                            eng_mode_only=True)]

  @plugin.RPCFunction
  def GetProperties(self):
    properties = ghost_prop.ReadProperties()
    return [[key, description, properties.get(key, '')]
            for key, description in self.key_desc]

  @plugin.RPCFunction
  def UpdateProperties(self, update):
    for key, value in update.items():
      if not value:
        return {
            'success': False,
            'error_msg': i18n.StringFormat(
                _("{key} can't be empty!"), key=self.key_desc_dict[key])
        }

    properties = ghost_prop.ReadProperties()
    properties.update(update)

    if self._CheckOverlordForDuplicate(properties):
      return {
          'success': False,
          'error_msg': i18n.StringFormat(
              _('Station with same {keys!r} found.'),
              keys=self.check_overlord)
      }

    ghost_prop.UpdateDeviceProperties(update)
    return {'success': True}

  @plugin.RPCFunction
  def NeedUpdate(self):
    properties = ghost_prop.ReadProperties()
    if not all(
        properties.get(key) for key, unused_description in self.key_desc):
      return True
    if self._CheckOverlordForDuplicate(properties):
      return True
    return False
