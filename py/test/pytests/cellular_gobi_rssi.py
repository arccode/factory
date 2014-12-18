# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for testing cellular module's RSSI.

This test query the RSSI (Received signal strength indication) of different
antenna path from gobi modem module.
"""

import numpy
import logging
import re
import unittest

import factory_common  # pylint: disable=W0611

from cros.factory.event_log import Log
from cros.factory.rf import cellular
from cros.factory.rf.utils import CheckPower
from cros.factory.test import factory
from cros.factory.test import utils
from cros.factory.test.args import Arg
from cros.factory.utils import sync_utils

RX_TEST_COMMAND = 'AT$QCAGC="%s",%d,"%s"'
FTM_WAIT_TIMEOUT_SECS = 10  # Timeout for waiting factory mode ready.
RETRY_INTERVAL_SECS = 1  # Retry interval in secs.

class CellularGobiRSSI(unittest.TestCase):
  ARGS = [
    Arg('modem_path', str,
        'The relative path from /dev/, the entry point to control the modem'),
    Arg('strength_map', list,
        'A list of tuple in the format (ANTENNA_NAME, BAND_NAME, CHANNEL_NO, '
        ' RETRIES, MIN_POWER, MAX_POWER)'),
    Arg('firmware_switching', bool,
        'Whether to switch modem firmware to UMTS.', default=True)
  ]

  def setUp(self):
    self.modem = None

  def GetRSSI(self, antenna_name, band_name, channel_no):
    def _CheckFTMError():
      self.modem.SendCommand(RX_TEST_COMMAND % (
        band_name, channel_no, antenna_name))
      line = self.modem.ReadLine()
      logging.info("Modem returned %r", line)
      if 'restricted to FTM' in line:
        return False
      return line

    modem_response = sync_utils.PollForCondition(
        poll_method=_CheckFTMError,
        timeout_secs=FTM_WAIT_TIMEOUT_SECS,
        poll_interval_secs=RETRY_INTERVAL_SECS,
        condition_name='Readiness of factory test mode')
    try:
      match = re.match(r'RSSI: ([-+]?\d+)$', modem_response)
      if not match:
        raise RuntimeError('Modem answered unexpected %r' % modem_response)
      rssi = int(match.group(1))
      self.modem.ReadLine()
      self.modem.ExpectLine('OK')
    except:  # pylint: disable=W0702
      # Modem might need retry to get a valid response, throw warning
      exception_string = utils.FormatExceptionOnly()
      factory.console.warning(exception_string)
      rssi = None
    return rssi

  def runTest(self):
    failures = []
    firmware = cellular.GetModemFirmware()
    power = dict()
    try:
      if self.args.firmware_switching:
        firmware = cellular.SwitchModemFirmware(cellular.WCDMA_FIRMWARE)

      self.modem = cellular.EnterFactoryMode(self.args.modem_path)
      for config_to_test in self.args.strength_map:
        antenna_name, band_name, channel_no, retries, min_power, max_power = (
          config_to_test)
        rssis = list()
        channel_name = '%s_%d_%s' % (band_name, channel_no, antenna_name)
        for tries in xrange(1, retries + 1):
          rssi = self.GetRSSI(antenna_name, band_name, channel_no)
          if rssi:
            factory.console.info('%d tries = %s', tries, rssi)
            rssis.append(rssi)
        # Compare if it is in range.
        rssi = numpy.median(rssis)
        CheckPower(channel_name, rssi, (min_power, max_power), failures)
        power[channel_name] = float(rssi)
    finally:
      cellular.ExitFactoryMode(self.modem)
      cellular.SwitchModemFirmware(firmware)

    Log('cellular_rssi', **power)
    if len(failures) > 0:
      raise factory.FactoryTestFailure('\n'.join(failures))
