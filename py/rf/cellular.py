# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common functions across different cellular modules."""

import logging
import re

import factory_common  # pylint: disable=W0611

from cros.factory.rf.modem import Modem
from cros.factory.test import factory
from cros.factory.utils.process_utils import Spawn

from subprocess import CalledProcessError

MODEM_STATUS = ['modem', 'status']
MODEM_IMEI_REG_EX = 'imei: ([0-9]*)'

SWITCH_TO_WCDMA_COMMAND = ['modem', 'set-carrier', 'Generic', 'UMTS']
SWITCH_TO_CDMA_COMMAND = ['modem', 'set-carrier', 'Verizon', 'Wireless']

ENABLE_FACTORY_TEST_MODE_COMMAND = 'AT+CFUN=5'
DISABLE_FACTORY_TEST_MODE_COMMAND = 'AT+CFUN=1'


def GetIMEI():
  '''Gets the IMEI of current active modem.'''
  stdout = Spawn(MODEM_STATUS, read_stdout=True,
                 log_stderr_on_error=True, check_call=True).stdout_data
  return re.search(MODEM_IMEI_REG_EX, stdout).group(1)

def EnterFactoryMode(modem_path, firmware_switching):
  """Enters factory mode of a modem.

  Args:
    modem_path: path to the modem.
    firmware_switching: whether to switch to WCDMA firmware.

  Returns:
    A Modem object that is ready in factory mode.

  Raises:
    subprocess.CalledProcessError: if switching fails.
  """
  factory.console.info('Entering factory test mode(FTM)')
  try:
    if firmware_switching:
      stdout = Spawn(SWITCH_TO_WCDMA_COMMAND, read_stdout=True,
                     log_stderr_on_error=True, check_call=True).stdout_data
      logging.info('Output when switching to WCDMA =\n%s', stdout)
  except CalledProcessError:
    factory.console.info('WCDMA switching failed.')
    raise
  modem = Modem(modem_path)
  modem.SendCommand(ENABLE_FACTORY_TEST_MODE_COMMAND)
  modem.ExpectLine('OK')
  factory.console.info('Entered factory test mode')
  return modem

def ExitFactoryMode(modem, firmware_switching):
  """Exits factory mode of a modem.

  Args:
    modem_path: path to the modem.
    firmware_switching: whether to switch to CDMA firmware.
  """
  factory.console.info('Exiting factory test mode(FTM)')
  modem.SendCommand(DISABLE_FACTORY_TEST_MODE_COMMAND)
  if firmware_switching:
    try:
      stdout = Spawn(SWITCH_TO_CDMA_COMMAND, read_stdout=True,
                     log_stderr_on_error=True, check_call=True).stdout_data
      logging.info('Output when switching to CDMA =\n%s', stdout)
    except CalledProcessError:
      factory.console.info('CDMA switching failed.')
  factory.console.info('Exited factory test mode')
