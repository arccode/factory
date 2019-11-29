# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import random

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy import goofy as goofy_module
from cros.factory.goofy.plugins import plugin
from cros.factory.test.utils import connection_manager
from cros.factory.utils import net_utils
from cros.factory.utils import type_utils


class ConnectionManager(plugin.Plugin):

  def __init__(self, goofy, wlans, scan_wifi_periods_secs,
               shuffle_wlans=False, override_blacklisted_network_devices=None):
    """Constructor

    Args:
      wlans: WLANs that the connection manager may connect to.
      scan_wifi_periods_secs: Scan wireless networks at the given interval.
      shuffle_wlans: Randomly shuffle the list of wlans to avoid overloading one
          AP.
      override_blacklisted_network_devices: Override blacklisted network
          devices in the system.  On some boards, some specific devices may be
          blacklisted by default, but we need to test those devices as well.
          This should be a list of strings (like ['eth0', 'wlan0']), an empty
          list or empty string (blocks nothing), or None (don't override).
    """

    super(ConnectionManager, self).__init__(goofy, [plugin.RESOURCE.NETWORK])
    self._scan_wifi_periods_secs = scan_wifi_periods_secs
    self._override_blacklisted_devices = override_blacklisted_network_devices
    self._shuffle_wlans = shuffle_wlans
    self._connection_manager = None
    self._SetAPs(wlans)

  def _SetAPs(self, wlans):
    converted_wlans = [net_utils.WLAN(**wlan) for wlan in wlans]
    if self._shuffle_wlans:
      random.shuffle(converted_wlans)
    self._connection_manager = connection_manager.ConnectionManager(
        wlans=converted_wlans,
        scan_interval=self._scan_wifi_periods_secs,
        override_blacklisted_devices=self._override_blacklisted_devices)

  @type_utils.Overrides
  def OnStart(self):
    if self.goofy.status == goofy_module.Status.INITIALIZING:
      # The first enabling of network is already done inside ConnectionManager
      # by start_enabled=True with reset=False so we don't want to init again.
      return
    # Back from a pytest requested exclusive network resource so we do want to
    # reset and clear everything.
    self._connection_manager.EnableNetworking(reset=True)

  @type_utils.Overrides
  def OnStop(self):
    # connection_manager plugin is usually stopped for running pytests that
    # needs exclusive access to network. But we should restore network state
    # when Goofy is terminating for factory_restart and wipe_in_place.
    name = self.__class__.__name__
    if self.goofy.status == goofy_module.Status.TERMINATING:
      logging.info('%s: Leave network enabled for shutdown.', name)
      self._connection_manager.EnableNetworking(reset=False)
    else:
      logging.info('%s: Disable network.', name)
      self._connection_manager.DisableNetworking()

  @plugin.RPCFunction
  def SetStaticIP(self, *args, **kwargs):
    try:
      self._connection_manager.SetStaticIP(*args, **kwargs)
      return None
    except connection_manager.ConnectionManagerException as e:
      return e.error_code

  @plugin.RPCFunction
  def Reconnect(self, wlans):
    if self._connection_manager:
      self._connection_manager.DisableNetworking()
      self._connection_manager = None
    self._SetAPs(wlans)
