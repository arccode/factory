# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common functions across different cellular modules."""

import logging
import re
import subprocess

from cros.factory.test.rf.modem import Modem
from cros.factory.test import session
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils

MODEM_STATUS = ['modem', 'status']
MODEM_IMEI_REG_EX = 'imei: ([0-9]*)'

MODEM_FIRMWARE_REG_EX = 'carrier: (.*)'
WCDMA_FIRMWARE = 'Generic UMTS'
CDMA_FIRMWARE = 'Verizon Wireless'

ENABLE_FACTORY_TEST_MODE_COMMAND = 'AT+CFUN=5'
DISABLE_FACTORY_TEST_MODE_COMMAND = 'AT+CFUN=1'


def GetIMEI():
  """Gets the IMEI of current active modem."""
  stdout = process_utils.Spawn(
      MODEM_STATUS, read_stdout=True,
      log_stderr_on_error=True, check_call=True).stdout_data
  match = re.search(MODEM_IMEI_REG_EX, stdout)
  if not match:
    logging.info('Returned stdout %r', stdout)
    raise type_utils.Error('Cannot get IMEI from modem')
  return match.group(1)


def GetModemFirmware():
  """Returns the firmware info."""
  stdout = process_utils.Spawn(
      MODEM_STATUS, read_stdout=True,
      log_stderr_on_error=True, check_call=True).stdout_data
  match = re.search(MODEM_FIRMWARE_REG_EX, stdout)
  if not match:
    logging.info('Returned stdout %r', stdout)
    raise type_utils.Error('Cannot switching firmware')
  return match.group(1)


def SwitchModemFirmware(target):
  """Switch firmware if different from target.

  Returns:
    the firmware version before switching.
  """
  firmware_info = GetModemFirmware()
  session.console.info('Firmware version = %r', firmware_info)
  try:
    if firmware_info != target:
      session.console.info('Switching firmware to %r', target)
      stdout = process_utils.Spawn(
          ['modem', 'set-carrier', target], read_stdout=True,
          log_stderr_on_error=True, check_call=True).stdout_data
      logging.info('Output when switching to %r =\n%s', target, stdout)
  except subprocess.CalledProcessError:
    session.console.info('%r switching failed.', target)
    raise
  return firmware_info


def EnterFactoryMode(modem_path):
  """Enters factory mode of a modem.

  Args:
    modem_path: path to the modem.

  Returns:
    A Modem object that is ready in factory mode.

  Raises:
    subprocess.CalledProcessError: if switching fails.
  """
  session.console.info('Entering factory test mode(FTM)')
  modem = Modem(modem_path)
  modem.SendCommand(ENABLE_FACTORY_TEST_MODE_COMMAND)
  modem.ExpectLine('OK')
  session.console.info('Entered factory test mode')
  return modem


def ExitFactoryMode(modem):
  """Exits factory mode of a modem.

  Args:
    modem_path: path to the modem.
  """
  session.console.info('Exiting factory test mode(FTM)')
  modem.SendCommand(DISABLE_FACTORY_TEST_MODE_COMMAND)
  session.console.info('Exited factory test mode')
