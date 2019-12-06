# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import datetime

from cros.factory.device import device_utils
try:
  from cros.factory.goofy.plugins import plugin_controller
  _HAS_PLUGIN_CONTROLLER = True
except ImportError:
  _HAS_PLUGIN_CONTROLLER = False


def SyncDate(dut=None):
  """Sync DUT datetime with station.

  Args:
    :type dut: cros.factory.device.device_types.DeviceInterface
  """

  if not dut:
    dut = device_utils.CreateDUTInterface()

  if not dut.link.IsLocal():
    now = datetime.datetime.utcnow()
    # set DUT time
    dut.CheckCall(['date', '-u', '{:%m%d%H%M%Y.%S}'.format(now)], log=True)


def SyncTimeWithFactoryServer():
  """Sync time with factory server.

  Returns: False if TimeSanitizer is not running.
  """
  time_sanitizer = None
  if _HAS_PLUGIN_CONTROLLER:
    time_sanitizer = plugin_controller.GetPluginRPCProxy('time_sanitizer')
  if time_sanitizer is not None:
    time_sanitizer.SyncTimeWithFactoryServer(force=True)
    return True
  return False
