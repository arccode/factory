# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test that waits the battery to be charged to specific level.

Description
-----------
The test waits until the battery is charged to the given level, and pass.

The ``target_charge_pct`` sets the target charge level in percentage.
``target_charge_pct`` can be set to some special values:

* ``"goofy"``: Use ``min_charge_pct`` from Goofy's charge_manager plugin as
  target charge level.
* ``"cutoff"``: Use ``CUTOFF_BATTERY_MIN_PERCENTAGE`` from cutoff.json as
  target charge level.

If ``target_charge_pct_is_delta`` is True, ``target_charge_pct`` would be
interpreted as difference to current charge level.

If battery doesn't reach the target level in ``timeout_secs`` seconds, the test
would fail.

Test Procedure
--------------
This is an automated test without user interaction.

1. A screen would be shown with current battery level, target battery level,
   and time remaining.
2. Test would pass when battery reach target level, or fail if test run longer
   than ``timeout_secs``.

Dependency
----------
Device API `cros.factory.device.power`.

Examples
--------
To charge the device to ``min_charge_pct`` in Goofy charge_manager (default
behavior), add this in test list::

  {
    "pytest_name": "blocking_charge",
    "exclusive_resources": ["POWER"]
  }

To charge the device to minimum battery level needed for cutoff, add this in
test list::

  {
    "pytest_name": "blocking_charge",
    "exclusive_resources": ["POWER"],
    "args": {
      "target_charge_pct": "cutoff"
    }
  }

To charge the device to 75 percent, add this in test list::

  {
    "pytest_name": "blocking_charge",
    "exclusive_resources": ["POWER"],
    "args": {
      "target_charge_pct": 75
    }
  }

To charge the device 10 percent more, and only allow 5 minutes time for
charging, add this in test list::

  {
    "pytest_name": "blocking_charge",
    "exclusive_resources": ["POWER"],
    "args": {
      "target_charge_pct_is_delta": true,
      "timeout_secs": 300,
      "target_charge_pct": 20
    }
  }
"""

import logging
import os

from cros.factory.device import device_utils
from cros.factory.test.env import paths
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test.utils import goofy_plugin_utils
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import config_utils
from cros.factory.utils.process_utils import LogAndCheckCall, CheckOutput
from cros.factory.utils import type_utils

_DEFAULT_TARGET_CHARGE = 78


def FormatTime(seconds):
  return '%d:%02d:%02d' % (seconds // 3600, (seconds // 60) % 60, seconds % 60)


def MakeChargeTextLabel(start, current, target, elapsed, remaining):
  return _(
      'Charging to {target}% (Start: {start}%. Current: {current}%.)<br>'
      'Time elapsed: {elapsed} Time remaining: {remaining}',
      target=target,
      start=start,
      current=current,
      elapsed=FormatTime(elapsed),
      remaining=FormatTime(remaining))


def MakeSpriteHTMLTag(src, height, width):
  return ('<div id="batteryIcon" style="background-image: url(%s);'
          'width: %dpx; height: %dpx; margin: auto;"></div>') % (src, width,
                                                                 height)


def _GetCutoffBatteryMinPercentage():
  config = config_utils.LoadConfig(
      config_name='cutoff',
      default_config_dirs=os.path.join(paths.FACTORY_DIR, 'sh', 'cutoff'))
  return config.get('CUTOFF_BATTERY_MIN_PERCENTAGE', _DEFAULT_TARGET_CHARGE)


def _GetGoofyBatteryMinPercentage():
  config = goofy_plugin_utils.GetPluginArguments('charge_manager') or {}
  return config.get('min_charge_pct', _DEFAULT_TARGET_CHARGE)


class ChargerTest(test_case.TestCase):
  ARGS = [
      Arg('target_charge_pct', (int, type_utils.Enum(['goofy', 'cutoff'])),
          'Target charge level.', default='goofy'),
      Arg('target_charge_pct_is_delta', bool,
          'Specify target_charge_pct is a delta of current charge',
          default=False),
      Arg('timeout_secs', int, 'Maximum allowed time to charge battery',
          default=3600),
      Arg('dim_backlight', bool,
          'Turn backlight/screen brightness lower to charge faster.',
          default=True),
      Arg('dim_backlight_pct', float,
          'The brightness in linear % when charging.',
          default=3.0),
  ]

  def setUp(self):
    self._power = device_utils.CreateDUTInterface().power

    # Group checker for Testlog.
    self._group_checker = testlog.GroupParam('charge', ['charge', 'elapsed'])

    if self.args.dim_backlight:
      # Get initial backlight brightness
      self._init_backlight_pct = float(CheckOutput(
          ['backlight_tool', '--get_brightness_percent']).strip())
      LogAndCheckCall(['backlight_tool',
                       '--set_brightness_percent=%f'
                       % self.args.dim_backlight_pct])

  def tearDown(self):
    if self.args.dim_backlight:
      LogAndCheckCall(['backlight_tool',
                       '--set_brightness_percent=%f'
                       % self._init_backlight_pct])

  def runTest(self):
    self.assertTrue(self._power.CheckBatteryPresent(), 'Cannot find battery.')
    self.assertTrue(self._power.CheckACPresent(), 'Cannot find AC power.')

    start_charge = self._power.GetChargePct()
    self.assertTrue(start_charge, 'Error getting battery state.')

    target_charge = self.args.target_charge_pct
    if self.args.target_charge_pct_is_delta:
      self.assertIsInstance(target_charge, int,
                            'target_charge must be int when '
                            'target_charge_pct_is_delta is True.')
      target_charge = min(target_charge + start_charge, 100)
    elif target_charge == 'cutoff':
      target_charge = _GetCutoffBatteryMinPercentage()
    elif target_charge == 'goofy':
      target_charge = _GetGoofyBatteryMinPercentage()

    logging.info('Target charge is %d%%', target_charge)
    testlog.LogParam('start_charge', start_charge)
    testlog.LogParam('target_charge', target_charge)
    if start_charge >= target_charge:
      return

    self._power.SetChargeState(self._power.ChargeState.CHARGE)
    self.ui.SetState(MakeSpriteHTMLTag('charging_sprite.png', 256, 256))
    logging.info('Charging starting at %d%%', start_charge)

    for elapsed in range(self.args.timeout_secs):
      charge = self._power.GetChargePct()

      if charge >= target_charge:
        event_log.Log('charged', charge=charge, target=target_charge,
                      elapsed=elapsed)
        with self._group_checker:
          testlog.CheckNumericParam('charge', charge, min=target_charge)
          testlog.LogParam('elapsed', elapsed)
        return
      self.ui.RunJS(
          'document.getElementById("batteryIcon").style.backgroundPosition'
          ' = "-%dpx 0px"' % ((elapsed % 4) * 256))
      self.ui.SetInstruction(MakeChargeTextLabel(
          start_charge,
          charge,
          target_charge,
          elapsed,
          self.args.timeout_secs - elapsed))

      if elapsed % 300 == 0:
        logging.info('Battery level is %d%% after %d minutes',
                     charge,
                     elapsed // 60)
      self.Sleep(1)

    event_log.Log('failed_to_charge', charge=charge, target=target_charge,
                  timeout_sec=self.args.timeout_secs)
    self.FailTask('Cannot charge battery to %d%% in %d seconds.' %
                  (target_charge, self.args.timeout_secs))
