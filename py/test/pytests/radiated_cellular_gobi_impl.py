# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import time
import logging

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
START_TX_TEST_COMMAND_WITH_PDM = 'AT$QCALLUP="%s",%d,"on",%d'
START_TX_TEST_RESPONSE = 'ALLUP: ON'
END_TX_TEST_COMMAND = 'AT$QCALLUP="%s",%d,"off"'
END_TX_TEST_RESPONSE = 'ALLUP: OFF'

ENABLE_TX_MODE_TIMEOUT_SECS = 5
TX_MODE_POLLING_INTERVAL_SECS = 0.5

class RadiatedCellularGobiImpl(RfFramework):
  measurements = None
  modem = None
  n1914a = None
  firmware = None

  def __init__(self, *args, **kwargs):
    super(RadiatedCellularGobiImpl, self ).__init__(*args, **kwargs)

  def PreTestOutsideShieldBox(self):
    factory.console.info('PreTestOutsideShieldBox called')
    # TODO(itspeter): Check all parameters are in expected type.
    self.measurements = self.config['tx_measurements']
    self.firmware = cellular.GetModemFirmware()
    self.EnterFactoryMode()

  def PreTestInsideShieldBox(self):
    factory.console.info('PreTestInsideShieldBox called')
    # TODO(itspeter): Ask user to enter shield box information.
    # TODO(itspeter): Check the existence of Ethernet.
    # TODO(itspeter): Verify the validity of shield-box and calibration_config.

    # Initialize the power_meter.
    self.n1914a = self.RunEquipmentCommand(N1914A, self.config['fixture_ip'])
    for port in self.config['ports']:
      self.RunEquipmentCommand(N1914A.SetRealFormat, self.n1914a)
      self.RunEquipmentCommand(
          N1914A.SetAverageFilter, self.n1914a,
          port=port, avg_length=None)
      self.RunEquipmentCommand(
          N1914A.SetMode, self.n1914a,
          port=port, mode=self.config['measure_mode'])
      self.RunEquipmentCommand(
          N1914A.SetTriggerToFreeRun, self.n1914a,
          port=port)
      self.RunEquipmentCommand(
          N1914A.SetContinuousTrigger, self.n1914a,
          port=port)

  def PrimaryTest(self):
    for measurement in self.measurements:
      measurement_name = measurement['measurement_name']
      port = measurement['port']
      range_setting = measurement['range']
      band_name = measurement['band_name']
      channel = measurement['channel']
      delay = measurement['delay']
      pdm = measurement['pdm']

      factory.console.info('Testing %s', measurement_name)
      try:
        # Set range for every single measurement
        self.RunEquipmentCommand(
            N1914A.SetRange, self.n1914a,
            port=port, range_setting=range_setting)
        self.RunEquipmentCommand(
            N1914A.SetMeasureFrequency, self.n1914a,
            port, measurement['frequency'])
        # Start continuous transmit
        self.StartTXTest(band_name, channel, pdm)
        self.Prompt('Modem is in TX mode for %s<br>'
                    'Press SPACE to continue' % measurement_name)
        self.SetHTML('Measuring %r' % measurement_name)
        if delay > 0:
          logging.info('Delay %.2f secs', delay)
          time.sleep(delay)

        # Measure the channel power.
        tx_power = self.RunEquipmentCommand(
            N1914A.MeasureInBinary, self.n1914a,
            port, self.config['avg_length'])
        if tx_power == None: # For 'without equipment' test
          tx_power = 0

        # End continuous transmit
        self.EndTXTest(band_name, channel)

        # Record verbose information of this channel.
        self.field_to_eventlog[measurement_name] = dict()
        self.field_to_eventlog[measurement_name]["parameters"] = measurement

        if self.calibration_mode:
          # Check if the path_loss is in expected range.
          path_loss_threshold = measurement['path_loss_threshold']
          path_loss = self.calibration_target[measurement_name] - tx_power
          self.calibration_config[measurement_name] = path_loss
          meet = CheckPower(measurement_name, path_loss, path_loss_threshold,
                            self.failures, prefix='Path loss')
          self.field_to_eventlog[measurement_name]['calibration_target'] = (
              self.calibration_target[measurement_name])
        else:
          tx_power += self.calibration_config[measurement_name]
          avg_power_threshold = measurement['avg_power_threshold']
          meet = CheckPower(measurement_name, tx_power, avg_power_threshold,
                            self.failures, prefix='TX')

        self.field_to_eventlog[measurement_name]['calibration_config'] = (
            self.calibration_config[measurement_name])
        self.field_to_eventlog[measurement_name]['tx_power'] = tx_power
        self.field_to_eventlog[measurement_name]['meet'] = meet
      except:  # pylint: disable=W0702
        # In order to collect more data, finish the whole test even if it fails.
        exception_string = utils.FormatExceptionOnly()
        failure = 'Unexpected failure on %s: %s' % (
            measurement_name, exception_string)
        factory.console.info(failure)
        self.failures.append(failure)

    # Explicitly close the connection
    self.RunEquipmentCommand(N1914A.Close, self.n1914a)

    # Centralized console output of measurements.
    for measurement in self.config['tx_measurements']:
      measurement_name = measurement['measurement_name']
      if measurement_name not in self.field_to_eventlog:
        # Exception during that channel and thus no power information.
        continue
      calibration_config_str = FormattedPower(
          self.calibration_config.get(measurement_name))
      tx_power_str = FormattedPower(
          self.field_to_eventlog[measurement_name].get('tx_power'))
      factory.console.info('tx_power for %20r = %s [calibration_config: %s]',
          measurement_name, tx_power_str, calibration_config_str)
      # Log import information into CSV.
      self.field_to_csv[measurement_name + '_tx_power'] = tx_power_str
      self.field_to_csv[measurement_name + '_cal'] = calibration_config_str


  def PostTest(self):
    # TODO(itspeter): save statistic of measurements to csv file.
    pass

  def GetUniqueIdentification(self):
    return cellular.GetIMEI()

  def GetEquipmentIdentification(self):
    return str(self.RunEquipmentCommand(N1914A.GetMACAddress, self.n1914a))

  def EnterFactoryMode(self):
    factory.console.info('Cellular_gobi: Entering factory test mode')
    self.firmware = cellular.SwitchModemFirmware(cellular.WCDMA_FIRMWARE)
    self.modem = cellular.EnterFactoryMode(self.config['modem_path'])
    factory.console.info('Cellular_gobi: Entered factory test mode')

  def ExitFactoryMode(self):
    factory.console.info('Cellular_gobi: Exiting factory test mode')
    cellular.ExitFactoryMode(self.modem)
    cellular.SwitchModemFirmware(self.firmware)
    factory.console.info('Cellular_gobi: Exited factory test mode')

  def StartTXTest(self, band_name, channel, pdm=None):
    def SendTXCommand():
      if pdm is None:
        self.modem.SendCommand(START_TX_TEST_COMMAND % (band_name, channel))
      else:
        self.modem.SendCommand(START_TX_TEST_COMMAND_WITH_PDM % (
            band_name, channel, pdm))

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
