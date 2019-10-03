# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.device import device_utils
from cros.factory.goofy.plugins import plugin
from cros.factory.utils import type_utils


class StatusMonitor(plugin.Plugin):

  def __init__(self, goofy, used_resources=None):
    super(StatusMonitor, self).__init__(goofy, used_resources)
    self._device = device_utils.CreateStationInterface()

  @type_utils.Overrides
  def GetUILocation(self):
    return 'goofy-full'

  @plugin.RPCFunction
  def UpdateDeviceInfo(self):
    """The device info is changed, update them on UI."""
    self._device.info.Invalidate()

  @plugin.RPCFunction
  def GetSystemInfo(self):
    """Returns system status information.

    This may include system load, battery status, etc. See
    cros.factory.device.status.SystemStatus. Return None
    if DUT is not local (station-based).
    """

    data = {}

    data.update(self._device.info.GetAll())

    if self._device.link.IsLocal():
      data.update(self._device.status.Snapshot().__dict__)

    return data
