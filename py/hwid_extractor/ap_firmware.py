# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import contextlib
import functools
import json
import logging
import os
import re
import subprocess
import time

from cros.factory.utils import file_utils
from cros.factory.utils import schema


FLASHROM_BIN = '/usr/sbin/flashrom'
FUTILITY_BIN = '/usr/bin/futility'
VPD_BIN = '/usr/sbin/vpd'
CMD_TIMEOUT_SECOND = 20

# The servo type names from servod.
SERVO_TYPE_CCD = 'ccd_cr50'

# The config of the ap commands of each board.
AP_CONFIG_JSON = os.path.join(os.path.dirname(__file__), 'ap_config.json')
AP_CONFIG_DUT_CONTROL = {
    'type': 'array',
    'items': {
        'type': 'array',
        'items': {
            'type': 'string'
        }
    }
}
AP_CONFIG_SCHEMA = schema.JSONSchemaDict(
    'ap_config',
    {
        'type': 'object',
        # Board.
        'additionalProperties': {
            'type': 'object',
            # Servo type.
            'additionalProperties': {
                'type': 'object',
                'properties': {
                    'dut_control_off': AP_CONFIG_DUT_CONTROL,
                    'dut_control_on': AP_CONFIG_DUT_CONTROL,
                    'programmer': {
                        'type': 'string'
                    }
                }
            }
        }
    })

HWID_RE = re.compile(r'^hardware_id: ([A-Z0-9- ]+)$')
SERIAL_NUMBER_RE = re.compile(r'^"serial_number"="([A-Za-z0-9]+)"$')


@functools.lru_cache(maxsize=None)
def _GetBoardConfigurations():
  """Get ap firmware configuration of each board.

  The configurations of supported boards are under chromite
  `chromite.lib.firmware.ap_firmware_config`. Those configs are dumped to
  `ap_config.json` through `cros ap dump-config`.
  """
  with open(AP_CONFIG_JSON, 'r') as f:
    boards = json.load(f)
  AP_CONFIG_SCHEMA.Validate(boards)
  return {k: v
          for k, v in boards.items()
          if SERVO_TYPE_CCD in v}


@functools.lru_cache(maxsize=None)
def GetSupportedBoards():
  """The supported boards for the web UI."""
  return sorted(_GetBoardConfigurations())


@contextlib.contextmanager
def _HandleDutControl(dut_on, dut_off, dut_control):
  """Execute dut_on before and dut_off after the context with dut_control."""
  try:
    dut_control.RunAll(dut_on)
    # Need to wait for SPI chip power to stabilize (for some designs)
    time.sleep(1)
    yield
  finally:
    dut_control.RunAll(dut_off)


def _GetHWID(firmware_binary_file):
  """Get HWID from ap firmware binary."""
  futility_cmd = [FUTILITY_BIN, 'gbb', firmware_binary_file]
  output = subprocess.check_output(futility_cmd, encoding='utf-8',
                                   timeout=CMD_TIMEOUT_SECOND)
  logging.debug('futility output:\n%s', output)
  output.split(':')
  m = HWID_RE.match(output.strip())
  return m and m.group(1)


def _GetSerialNumber(firmware_binary_file):
  """Get serial number from ap firmware binary."""
  vpd_cmd = [VPD_BIN, '-l', '-f', firmware_binary_file]
  output = subprocess.check_output(vpd_cmd, encoding='utf-8',
                                   timeout=CMD_TIMEOUT_SECOND)
  logging.debug('vpd output:\n%s', output)
  for line in output.splitlines():
    m = SERIAL_NUMBER_RE.match(line.strip())
    if m:
      return m.group(1)
  return None


def _CheckServoTypeIsCCD(dut_control):
  servo_type = dut_control.GetValue('servo_type')
  if servo_type != SERVO_TYPE_CCD:
    raise RuntimeError(f'Servo type is not ccd, got: {servo_type}')


def ExtractHWIDAndSerialNumber(board, dut_control):
  """Extract HWID and serial no. from DUT.

  Read the ap firmware binary from DUT and extract the info from it. Only the
  necessary blocks are read to reduce the reading time. Some dut-control
  commands are executed before and after `flashrom` to control the DUT status.

  Args:
    board: The name of the reference board of DUT which is extracted.
    dut_control: DUTControl interface object for dut-control commands.

  Returns:
    hwid, serial_number. The value may be None.
  """
  _CheckServoTypeIsCCD(dut_control)

  boards = _GetBoardConfigurations()
  if board not in boards:
    raise ValueError(f'Board "{board}" is not supported.')
  ap_config = boards[board][SERVO_TYPE_CCD]

  with file_utils.UnopenedTemporaryFile() as tmp_file, _HandleDutControl(
      ap_config['dut_control_on'], ap_config['dut_control_off'], dut_control):
    serial_name = dut_control.GetValue('serialname')
    programmer = ap_config['programmer'] % serial_name
    flashrom_cmd = [
        FLASHROM_BIN, '-i', 'FMAP', '-i', 'RO_VPD', '-i', 'GBB', '-p',
        programmer, '-r', tmp_file
    ]
    output = subprocess.check_output(flashrom_cmd, encoding='utf-8',
                                     timeout=CMD_TIMEOUT_SECOND)
    logging.debug('flashrom output:\n%s', output)
    hwid = _GetHWID(tmp_file)
    serial_number = _GetSerialNumber(tmp_file)
    logging.info('Extract result: HWID: "%s", serial number: "%s"', hwid,
                 serial_number)

  return hwid, serial_number
