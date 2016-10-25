# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import random


import factory_common  # pylint: disable=unused-import
from cros.factory.goofy.plugins import plugin
from cros.factory.test.utils import connection_manager
from cros.factory.utils import net_utils


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

    super(ConnectionManager, self).__init__(goofy)
    converted_wlans = [net_utils.WLAN(**wlan) for wlan in wlans]
    if shuffle_wlans:
      random.shuffle(converted_wlans)
    self._connection_manager = connection_manager.ConnectionManager(
        wlans=converted_wlans,
        scan_interval=scan_wifi_periods_secs,
        override_blacklisted_devices=override_blacklisted_network_devices)

  def OnStart(self):
    self._connection_manager.EnableNetworking()

  def OnStop(self):
    self._connection_manager.DisableNetworking()
