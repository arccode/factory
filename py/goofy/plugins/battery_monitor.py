# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.goofy.plugins import periodic_plugin

class BatteryMonitor(periodic_plugin.PeriodicPlugin):
  # Sync disks when battery level is higher than this value.
  # Otherwise, power loss during disk sync operation may incur even worse
  # outcome.
  MIN_BATTERY_LEVEL_FOR_DISK_SYNC = 1.0

  def __init__(self, goofy, period_secs, critical_low_battery_pct=None,
               warning_log_battery_pct=False):
    super(BatteryMonitor, self).__init__(goofy, period_secs)

    self._critical_low_battery_pct = critical_low_battery_pct
    self._warning_log_battery_pct = warning_log_battery_pct
    self._dut = device_utils.CreateDUTInterface()
    self._last_log_message = None

  def RunTask(self):
    self._CheckBattery()

  def _CheckBattery(self):
    """Checks the current battery status.

    Logs current battery charging level and status to log. If the battery level
    is lower below warning_low_battery_pct, send warning event to shopfloor.
    If the battery level is lower below critical_low_battery_pct, flush disks.
    """

    message = ''
    log_level = logging.INFO
    try:
      power = self._dut.power
      if not power.CheckBatteryPresent():
        message = 'Battery is not present'
      else:
        ac_present = power.CheckACPresent()
        charge_pct = power.GetChargePct(get_float=True)
        message = ('Current battery level %.1f%%, AC charger is %s' %
                   (charge_pct, 'connected' if ac_present else 'disconnected'))

        if charge_pct > self._critical_low_battery_pct:
          critical_low_battery = False
        else:
          critical_low_battery = True
          # Only sync disks when battery level is still above minimum
          # value. This can be used for offline analysis when shopfloor cannot
          # be connected.
          if charge_pct > self.MIN_BATTERY_LEVEL_FOR_DISK_SYNC:
            logging.warning('disk syncing for critical low battery situation')
            os.system('sync; sync; sync')
          else:
            logging.warning('disk syncing is cancelled '
                            'because battery level is lower than %.1f',
                            self.MIN_BATTERY_LEVEL_FOR_DISK_SYNC)

        # Notify shopfloor server
        if (critical_low_battery or
            (not ac_present and charge_pct <= self._warning_low_battery_pct)):
          log_level = logging.WARNING

          self.goofy.event_log.Log('low_battery',
                                   battery_level=charge_pct,
                                   charger_connected=ac_present,
                                   critical=critical_low_battery)
          self.goofy.log_watcher.KickWatchThread()
          # TODO (shunhsingou): remove following code after moving
          # system_log_manager into Goofy plugin.
          if self.goofy.test_list.options.enable_sync_log:
            self.goofy.system_log_manager.KickToSync()
    except Exception:
      logging.exception('Unable to check battery or notify shopfloor')
    finally:
      if message != self._last_log_message:
        logging.log(log_level, message)
        self._last_log_message = message
