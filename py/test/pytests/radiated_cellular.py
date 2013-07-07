# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.rf.cellular import GetIMEI
from cros.factory.rf.modem import Modem
from cros.factory.rf.utils import IsInRange
from cros.factory.test import factory
from cros.factory.test.pytests.rf_framework import RfFramework
from cros.factory.utils.net_utils import PollForCondition
from cros.factory.rf.n1914a import N1914A

ENABLE_FACTORY_TEST_MODE_COMMAND = 'AT+CFUN=5'
DISABLE_FACTORY_TEST_MODE_COMMAND = 'AT+CFUN=1'

START_TX_TEST_COMMAND = 'AT+ALLUP="%s",%d,"on",75'
START_TX_TEST_RESPONSE = 'ALLUP: ON'

READ_RSSI_COMMAND = 'AT+AGC="%s",%d,"%s"'
READ_RSSI_RESPONSE = r'RSSI: ([-\d]+)'

ENABLE_TX_MODE_TIMEOUT_SECS = 5
TX_MODE_POLLING_INTERVAL_SECS = 0.5

class RadiatedCellular(RfFramework, unittest.TestCase):

  def __init__(self, *args, **kwargs):
    super(RadiatedCellular, self ).__init__(*args, **kwargs)
    self.measurements = None
    self.power_meter_ip = None
    self.power_meter_port = None
    self.modem_path = None
    self.modem = None
    self.n1914a = None

  def PreTestOutsideShieldBox(self):
    factory.console.info('PreTestOutsideShieldBox called')
    # TODO(itspeter): Check all parameters are in expected type.
    self.measurements = self.config['tx_measurements']
    self.power_meter_ip = self.config['fixture_ip']
    self.power_meter_port = self.config['fixture_port']
    self.modem_path = self.config['modem_path']

  def PreTestInsideShieldBox(self):
    factory.console.info('PreTestInsideShieldBox called')
    # TODO(itspeter): Ask user to enter shield box information.
    # TODO(itspeter): Check the existence of Ethernet.
    # TODO(itspeter): Verify the validity of shield-box and calibration_config.

    # Initialize the power_meter.
    self.n1914a = N1914A(self.power_meter_ip)
    self.n1914a.SetRealFormat()
    self.n1914a.SetAverageFilter(port=self.power_meter_port, avg_length=None)
    self.n1914a.SetRange(port=self.power_meter_port, range_setting=1)
    self.n1914a.SetTriggerToFreeRun(port=self.power_meter_port)
    self.n1914a.SetContinuousTrigger(port=self.power_meter_port)

  def PrimaryTest(self):
    for measurement in self.measurements:
      measurement_name = measurement['measurement_name']
      factory.console.info('Testing %s', measurement_name)
      try:

        self.n1914a.SetMeasureFrequency(
            self.power_meter_port, measurement['frequency'])
        # Start continuous transmit
        # This may fail the first time if the modem isn't ready;
        # try a few more times.
        PollForCondition(condition=(
            lambda: self.StartTxTest(
                measurement['band_name'], measurement['channel'])),
            timeout=ENABLE_TX_MODE_TIMEOUT_SECS,
            poll_interval_secs=TX_MODE_POLLING_INTERVAL_SECS,
            condition_name='Start TX test')
        self.modem.ExpectLine('')
        self.modem.ExpectLine('OK')

        # Measure the channel power.
        tx_power = self.n1914a.MeasureOnceInBinary(self.power_meter_port)
        min_power = measurement['avg_power_threshold'][0]
        max_power = measurement['avg_power_threshold'][1]
        if not IsInRange(tx_power, min_power, max_power):
          failure = 'Power for %r is %7.2f, out of range (%s,%s)' % (
              measurement_name, tx_power, min_power, max_power)
          factory.console.info(failure)
          self.failures.append(failure)
      except Exception as e:
        # In order to collect more data, finish the whole test even if it fails.
        self.failures.append(
            'Unexpected failure on %s: %s' % (measurement_name, e))

  def PostTest(self):
    # TODO(itspeter): Switch to production drivers.
    # TODO(itspeter): Upload result to shopfloor server.
    # TODO(itspeter): Determine the test result.
    # TODO(itspeter): save statistic of measurements to csv file.
    pass

  def GetUniqueIdentification(self):
    return GetIMEI()

  def GetEquipmentIdentification(self):
    return str(self.RunEquipmentCommand(N1914A.GetMACAddress, self.n1914a))

  def EnterFactoryMode(self):
    factory.console.info('Entering factory test mode(FTM)')
    self.modem = Modem(self.modem_path)
    self.modem.SendCommand(ENABLE_FACTORY_TEST_MODE_COMMAND)
    self.modem.ExpectLine('OK')

  def ExitFactoryMode(self):
    factory.console.info('Exiting factory test mode(FTM)')
    self.modem.SendCommand(DISABLE_FACTORY_TEST_MODE_COMMAND)

  def StartTxTest(self, band_name, channel):
    self.modem.SendCommand(START_TX_TEST_COMMAND % (band_name, channel))
    line = self.modem.ReadLine()
    if 'restricted to FTM' in line:
      factory.console.info('Factory test mode not ready: %r' % line)
      return False
    return True
