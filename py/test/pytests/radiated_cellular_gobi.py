# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.rf import cellular
from cros.factory.rf.utils import CheckPower, FormattedPower
from cros.factory.test import factory
from cros.factory.test import utils
from cros.factory.test.pytests.rf_framework import RfFramework
from cros.factory.utils.net_utils import PollForCondition
from cros.factory.rf.n1914a import N1914A

ENABLE_FACTORY_TEST_MODE_COMMAND = 'AT+CFUN=5'
DISABLE_FACTORY_TEST_MODE_COMMAND = 'AT+CFUN=1'

SWITCH_TO_WCDMA_COMMAND = ['modem', 'set-carrier', 'Generic', 'UMTS']
SWITCH_TO_CDMA_COMMAND = ['modem', 'set-carrier', 'Verizon', 'Wireless']
START_TX_TEST_COMMAND = 'AT$QCALLUP="%s",%d,"on"'
START_TX_TEST_RESPONSE = 'ALLUP: ON'
END_TX_TEST_COMMAND = 'AT$QCALLUP="%s",%d,"off"'
END_TX_TEST_RESPONSE = 'ALLUP: OFF'

ENABLE_TX_MODE_TIMEOUT_SECS = 5
TX_MODE_POLLING_INTERVAL_SECS = 0.5

class RadiatedCellularGobi(RfFramework, unittest.TestCase):
  measurements = None
  power_meter_port = None
  modem = None
  n1914a = None
  firmware = None

  def __init__(self, *args, **kwargs):
    super(RadiatedCellularGobi, self ).__init__(*args, **kwargs)

  def PreTestOutsideShieldBox(self):
    factory.console.info('PreTestOutsideShieldBox called')
    # TODO(itspeter): Check all parameters are in expected type.
    self.measurements = self.config['tx_measurements']
    self.power_meter_port = self.config['fixture_port']
    self.firmware = cellular.GetModemFirmware()

  def PreTestInsideShieldBox(self):
    factory.console.info('PreTestInsideShieldBox called')
    # TODO(itspeter): Ask user to enter shield box information.
    # TODO(itspeter): Check the existence of Ethernet.
    # TODO(itspeter): Verify the validity of shield-box and calibration_config.

    # Initialize the power_meter.
    self.n1914a = self.RunEquipmentCommand(N1914A, self.config['fixture_ip'])
    self.RunEquipmentCommand(N1914A.SetRealFormat, self.n1914a)
    self.RunEquipmentCommand(
        N1914A.SetAverageFilter, self.n1914a,
        port=self.power_meter_port, avg_length=None)
    self.RunEquipmentCommand(
        N1914A.SetRange, self.n1914a,
        port=self.power_meter_port, range_setting=1)
    self.RunEquipmentCommand(
        N1914A.SetTriggerToFreeRun, self.n1914a,
        port=self.power_meter_port)
    self.RunEquipmentCommand(
        N1914A.SetContinuousTrigger, self.n1914a,
        port=self.power_meter_port)

  def PrimaryTest(self):
    for measurement in self.measurements:
      measurement_name = measurement['measurement_name']
      factory.console.info('Testing %s', measurement_name)
      try:
        self.RunEquipmentCommand(
            N1914A.SetMeasureFrequency, self.n1914a,
            self.power_meter_port, measurement['frequency'])
        # Start continuous transmit
        self.StartTXTest(measurement['band_name'], measurement['channel'])
        self.Prompt('Modem is in TX mode for %s<br>'
                    'Press SPACE to continue' % measurement_name)
        self.template.SetState('Measuring %r' % measurement_name)

        # Measure the channel power.
        tx_power = self.RunEquipmentCommand(
            N1914A.MeasureInBinary, self.n1914a,
            self.power_meter_port, self.config['avg_length'])

        # End continuous transmit
        self.EndTXTest(measurement['band_name'], measurement['channel'])

        if self.calibration_mode:
          # Check if the path_loss is in expected range.
          path_loss_range = measurement['path_loss_range']
          path_loss = self.calibration_target[measurement_name] - tx_power
          CheckPower(measurement_name, path_loss, path_loss_range,
                     self.failures, prefix='Path loss')
        else:
          tx_power += self.calibration_config[measurement_name]

        self.field_to_record[measurement_name] = FormattedPower(tx_power)
        avg_power_threshold = measurement['avg_power_threshold']
        CheckPower(measurement_name, tx_power, avg_power_threshold,
                   self.failures)

      except:  # pylint: disable=W0702
        # In order to collect more data, finish the whole test even if it fails.
        exception_string = utils.FormatExceptionOnly()
        failure = 'Unexpected failure on %s: %s' % (
            measurement_name, exception_string)
        factory.console.info(failure)
        self.failures.append(failure)
    # TODO(itspeter): Generate the calibration_config

  def PostTest(self):
    # TODO(itspeter): save statistic of measurements to csv file.
    pass

  def GetUniqueIdentification(self):
    return cellular.GetIMEI()

  def EnterFactoryMode(self):
    self.firmware = cellular.SwitchModemFirmware(cellular.WCDMA_FIRMWARE)
    self.modem = cellular.EnterFactoryMode(self.config['modem_path'])

  def ExitFactoryMode(self):
    cellular.ExitFactoryMode(self.modem)
    cellular.SwitchModemFirmware(self.firmware)

  def StartTXTest(self, band_name, channel):
    def SendTXCommand():
      self.modem.SendCommand(START_TX_TEST_COMMAND % (band_name, channel))
      line = self.modem.ReadLine()
      if line == START_TX_TEST_RESPONSE:
        return True
      factory.console.info('Factory test mode not ready: %r' % line)
      return False

    # This may fail the first time if the modem isn't ready;
    # try a few more times.
    PollForCondition(
        condition=SendTXCommand,
        timeout=ENABLE_TX_MODE_TIMEOUT_SECS,
        poll_interval_secs=TX_MODE_POLLING_INTERVAL_SECS,
        condition_name='Start TX test')
    self.modem.ExpectLine('')
    self.modem.ExpectLine('OK')

  def EndTXTest(self, band_name, channel):
    self.modem.SendCommand(END_TX_TEST_COMMAND % (band_name, channel))
    self.modem.ExpectLine(END_TX_TEST_RESPONSE)
    self.modem.ExpectLine('')
    self.modem.ExpectLine('OK')
