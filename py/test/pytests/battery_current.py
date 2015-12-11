# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''This is a factory test to test battery charging/discharging current.

dargs:
  min_charging_current: The minimum allowed charging current. In mA.
  min_discharging_current: The minimum allowed discharging current. In mA.
  timeout_secs: The timeout of detecting required charging/discharging current.
'''

import logging
import textwrap
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import dut
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.utils.sync_utils import PollForCondition

_TEST_TITLE = test_ui.MakeLabel('Battery Current Test', u'充電放電电流測試')


def _PROMPT_TEXT(charge, current, target):
  return test_ui.MakeLabel(
      'Waiting for %s current to meet %d mA. (Currently %s at %d mA)' %
      ('charging' if charge else 'discharging',
       target,
       'charging' if current >= 0 else 'discharging',
       abs(current)),
      u'等待%s电流大于 %d mA. (目前%s中:%d mA)' %
      (u'充电' if charge else u'放电',
       target,
       u'充电' if current >= 0 else u'放电',
       abs(current)))

_CHARGE_TEXT = lambda c, t: _PROMPT_TEXT(True, c, t)
_DISCHARGE_TEXT = lambda c, t: _PROMPT_TEXT(False, c, t)
_USBPDPORT_PROMPT = (lambda en, zh, v:
                     test_ui.MakeLabel('Insert power to %s(%dmV)' % (en, v),
                                       u'请将电源线插入%s(%dmV)' % (zh, v)))


class BatteryCurrentTest(unittest.TestCase):
  """A factory test to test battery charging/discharging current.
  """
  ARGS = [
      Arg('min_charging_current', int,
          'minimum allowed charging current', optional=True),
      Arg('min_discharging_current', int,
          'minimum allowed discharging current', optional=True),
      Arg('timeout_secs', int,
          'Test timeout value', default=10, optional=True),
      Arg('max_battery_level', int,
          'maximum allowed starting battery level', optional=True),
      Arg('usbpd_info', tuple, textwrap.dedent("""
          (usbpd_port, usbpd_port_prompt, min_millivolt) Used to select a
          particular port from a multi-port DUT.
          usbpd_port: (int) usbpd_port number. Specify which port to insert
                      power line.
          usbpd_port_prompt_en: (str) prompt operator which port to insert in
                                      English
          usbpd_port_prompt_zh: (str) prompt operator which port to insert in
                                      Chinese.
          min_millivolt: (int) The minimum millivolt the power must provide
          """),
          optional=True)
  ]

  def setUp(self):
    """Sets the test ui, template and the thread that runs ui. Initializes
    _ec and _power."""
    self._dut = dut.Create()
    self._power = self._dut.power
    self._ec = self._dut.ec
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    if self.args.usbpd_info:
      self._CheckUSBPDInfoArg(self.args.usbpd_info)
      self._usbpd_port = self.args.usbpd_info[0]
      self._usbpd_prompt_en = self.args.usbpd_info[1]
      self._usbpd_prompt_zh = self.args.usbpd_info[2]
      self._usbpd_min_millivolt = self.args.usbpd_info[3]

  def _CheckUSBPDInfoArg(self, info):
    check_types = (int, basestring, basestring, int)
    if len(info) != 4:
      raise ValueError('ERROR: invalid usbpd_info item: ' + str(info))
    for i in xrange(len(info)):
      if not isinstance(info[i], check_types[i]):
        logging.error('(%s)usbpd_info[%d] type is not %s', type(info[i]), i,
                      check_types[i])
        raise ValueError('ERROR: invalid usbpd_info[%d]: ' % i + str(info))

  def _LogCurrent(self, current):
    if current >= 0:
      logging.info('Charging current = %d mA', current)
    else:
      logging.info('Discharging current = %d mA', -current)

  def _CheckUSBPD(self):
    status = self._ec.GetUSBPDPowerStatus()
    self._template.SetState(_USBPDPORT_PROMPT(self._usbpd_prompt_en,
                                              self._usbpd_prompt_zh, 0))
    if 'millivolt' not in status[self._usbpd_port]:
      logging.info('No millivolt detected in port %d', self._usbpd_port)
      return False
    millivolt = status[self._usbpd_port]['millivolt']
    logging.info('millivolt %d, min_millivolt %d', millivolt,
                 self._usbpd_min_millivolt)
    self._template.SetState(_USBPDPORT_PROMPT(self._usbpd_prompt_en,
                                              self._usbpd_prompt_zh, millivolt))
    return millivolt >= self._usbpd_min_millivolt

  def _CheckCharge(self):
    current = self._power.GetBatteryCurrent()
    target = self.args.min_charging_current
    self._LogCurrent(current)
    self._template.SetState(_CHARGE_TEXT(current, target))
    return current >= target

  def _CheckDischarge(self):
    current = self._power.GetBatteryCurrent()
    target = self.args.min_discharging_current
    self._LogCurrent(current)
    self._template.SetState(_DISCHARGE_TEXT(current, target))
    return -current >= target

  def runTest(self):
    """Main entrance of charger test."""
    self.assertTrue(self._power.CheckBatteryPresent())
    if self.args.max_battery_level:
      self.assertLessEqual(self._power.GetChargePct(),
                           self.args.max_battery_level,
                           'Starting battery level too high')
    self._ui.Run(blocking=False)
    if self.args.usbpd_info is not None:
      PollForCondition(poll_method=self._CheckUSBPD, poll_interval_secs=0.5,
                       condition_name='CheckUSBPD',
                       timeout_secs=self.args.timeout_secs)
    if self.args.min_charging_current:
      self._power.SetChargeState(self._power.ChargeState.CHARGE)
      PollForCondition(poll_method=self._CheckCharge, poll_interval_secs=0.5,
                       condition_name='ChargeCurrent',
                       timeout_secs=self.args.timeout_secs)
    if self.args.min_discharging_current:
      self._power.SetChargeState(self._power.ChargeState.DISCHARGE)
      PollForCondition(poll_method=self._CheckDischarge, poll_interval_secs=0.5,
                       condition_name='DischargeCurrent',
                       timeout_secs=self.args.timeout_secs)

  def tearDown(self):
    # Must enable charger to charge or we will drain the battery!
    self._power.SetChargeState(self._power.ChargeState.CHARGE)
