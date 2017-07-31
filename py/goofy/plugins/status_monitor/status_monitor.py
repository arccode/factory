# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.goofy.plugins import plugin
from cros.factory.utils import type_utils


class StatusMonitor(plugin.Plugin):

  def __init__(self, goofy, used_resources=None):
    super(StatusMonitor, self).__init__(goofy, used_resources)
    self._dut = device_utils.CreateDUTInterface()
    self._need_update_device_info = True

  @type_utils.Overrides
  def HasUI(self):
    return True

  @plugin.RPCFunction
  def UpdateDeviceInfo(self):
    """The device info is changed, update them on UI."""
    self._dut.info.Invalidate()
    self._need_update_device_info = True

  @plugin.RPCFunction
  def GetSystemInfo(self):
    """Returns system status information.

    This may include system load, battery status, etc. See
    cros.factory.device.status.SystemStatus. Return None
    if DUT is not local (station-based).
    """

    data = {}

    if self._need_update_device_info:
      data.update(self._dut.info.GetAll())
      self._need_update_device_info = False

    if self._dut.link.IsLocal():
      data.update(self._dut.status.Snapshot().__dict__)

    return data
