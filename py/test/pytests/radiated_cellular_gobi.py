# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import time
import unittest

import factory_common  # pylint: disable=W0611
from subprocess import CalledProcessError
from cros.factory.rf.modem import Modem
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import utils
from cros.factory.test.pytests.rf_framework import RfFramework
from cros.factory.utils.net_utils import PollForCondition
from cros.factory.utils.process_utils import Spawn
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

  def __init__(self, *args, **kwargs):
    super(RadiatedCellularGobi, self ).__init__(*args, **kwargs)

  def PreTestOutsideShieldBox(self):
    factory.console.info('PreTestOutsideShieldBox called')
    # TODO(itspeter): Check all parameters are in expected type.
    self.measurements = self.config['tx_measurements']
    self.power_meter_port = self.config['fixture_port']

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

        # Measure the channel power.
        tx_power = self.RunEquipmentCommand(
            N1914A.MeasureOnceInBinary, self.n1914a,
            self.power_meter_port)
        min_power = measurement['avg_power_threshold'][0]
        max_power = measurement['avg_power_threshold'][1]
        if not self.IsInRange(tx_power, min_power, max_power):
          failure = 'Power for %r is %s, out of range (%s,%s)' % (
              measurement_name, self.FormattedPower(tx_power),
              self.FormattedPower(min_power), self.FormattedPower(max_power))
          factory.console.info(failure)
          self.failures.append(failure)

        # End continuous transmit
        self.EndTXTest(measurement['band_name'], measurement['channel'])

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

  def DownloadParameters(self):
    """Downloads parameters from shopfloor and saved to state/caches."""
    factory.console.info('Start downloading parameters...')
    _SHOPFLOOR_TIMEOUT_SECS = 10 # Timeout for shopfloor connection.
    _SHOPFLOOR_RETRY_INTERVAL_SECS = 10 # Seconds to wait between retries.
    while True:
      try:
        logging.info('Syncing time with shopfloor...')
        goofy = factory.get_state_instance()
        goofy.SyncTimeWithShopfloorServer()

        # Listing files on args.parameters
        download_list = []
        shopfloor_client = shopfloor.get_instance(
            detect=True, timeout=_SHOPFLOOR_TIMEOUT_SECS)
        for glob_expression in self.args.parameters:
          logging.info('Listing %s', glob_expression)
          download_list.extend(
              shopfloor_client.ListParameters(glob_expression))
        logging.info('Download list prepared:\n%s', '\n'.join(download_list))
        # Download the list and saved to caches in state directory.
        for filepath in download_list:
          utils.TryMakeDirs(os.path.join(
              self.caches_dir, os.path.dirname(filepath)))
          binary_obj = shopfloor_client.GetParameter(filepath)
          with open(os.path.join(self.caches_dir, filepath), 'wb') as fd:
            fd.write(binary_obj.data)
        return
      except:  # pylint: disable=W0702
        exception_string = utils.FormatExceptionOnly()
        # Log only the exception string, not the entire exception,
        # since this may happen repeatedly.
        factory.console.info('Unable to sync with shopfloor server: %s',
                             exception_string)
      time.sleep(_SHOPFLOOR_RETRY_INTERVAL_SECS)

    # TODO(itspeter): Verify the signature of parameters.

  def EnterFactoryMode(self):
    factory.console.info('Entering factory test mode(FTM)')
    try:
      stdout = Spawn(SWITCH_TO_WCDMA_COMMAND, read_stdout=True,
                     log_stderr_on_error=True, check_call=True).stdout_data
      logging.info('Output when switching to WCDMA =\n%s', stdout)
    except CalledProcessError:
      factory.console.info('WCDMA switching failed.')
      raise
    self.modem = Modem(self.config['modem_path'])
    self.modem.SendCommand(ENABLE_FACTORY_TEST_MODE_COMMAND)
    self.modem.ExpectLine('OK')

  def ExitFactoryMode(self):
    factory.console.info('Exiting factory test mode(FTM)')
    self.modem.SendCommand(DISABLE_FACTORY_TEST_MODE_COMMAND)
    try:
      stdout = Spawn(SWITCH_TO_CDMA_COMMAND, read_stdout=True,
                     log_stderr_on_error=True, check_call=True).stdout_data
      logging.info('Output when switching to CDMA =\n%s', stdout)
    except CalledProcessError:
      factory.console.info('CDMA switching failed.')

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
