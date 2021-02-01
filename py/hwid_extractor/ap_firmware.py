# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import contextlib
import glob
import importlib
import json
import logging
import os
import re
import subprocess
import time

from chromite.lib.firmware import ap_firmware_config, servo_lib

from cros.factory.utils import file_utils


FLASHROM_BIN = '/usr/sbin/flashrom'
FUTILITY_BIN = '/usr/bin/futility'
VPD_BIN = '/usr/sbin/vpd'
CMD_TIMEOUT_SECOND = 20

CONFIG_FILE_PATTERN = os.path.join(
    os.path.dirname(ap_firmware_config.__file__), '[!_]*.py')
# This dict maps board names to the configuration object of each board.
BOARD = {}

HWID_RE = re.compile(r'^hardware_id: ([A-Z0-9- ]+)$')
SERIAL_NUMBER_RE = re.compile(r'^"serial_number"="([A-Za-z0-9]+)"$')

SUPPORTED_BOARDS_JSON = os.path.join(
    os.path.dirname(__file__), 'www', 'supported_boards.json')


def _InitializeBoardConfigurations():
  """Initialize configuration object of each board.

  All configurations of supported boards are under chromite
  `chromite.lib.firmware.ap_firmware_config`.

  The supported boards are dumped to supported-boards.json for the web UI.
  """
  for f in glob.glob(CONFIG_FILE_PATTERN):
    board = os.path.splitext(os.path.basename(f))[0]
    BOARD[board] = importlib.import_module(
        f'chromite.lib.firmware.ap_firmware_config.{board}')

  with open(SUPPORTED_BOARDS_JSON, 'w') as f:
    json.dump({'supportedBoards': sorted(BOARD)}, f)


_InitializeBoardConfigurations()


@contextlib.contextmanager
def _HandleDutControl(dut_on, dut_off, dut_control):
  """Execute dut_on before and dut_off after the context with dut_control."""
  try:
    dut_control.run_all(dut_on)
    # Need to wait for SPI chip power to stabilize (for some designs)
    time.sleep(1)
    yield
  finally:
    dut_control.run_all(dut_off)


def _GetProgrammerFromFlashromCmd(flashrom_cmd):
  """Get the program argument of flashrom.

  Args:
    flashrom_cmd: The flashrom writing command which is returned by
    configuration objects of the boards.
  Returns:
    The programmer argument of flashrom.
  """
  for i, arg in enumerate(flashrom_cmd):
    if arg == '-p' and i + 1 < len(flashrom_cmd):
      return flashrom_cmd[i + 1]
  raise RuntimeError(
      f'Cannot get programmer from flashrom_cmd: {flashrom_cmd!r}')


def _GetFlashromInfo(board, servo_status):
  """Returns the info for flashrom to reading ap firmware."""
  if board not in BOARD:
    raise ValueError(f'Board "{board}" is not supported.')
  dut_on, dut_off, flashrom_cmd, unused_futility_cmd = (
      BOARD[board].get_commands(servo_status))
  programmer = _GetProgrammerFromFlashromCmd(flashrom_cmd)
  return dut_on, dut_off, programmer


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
  servo_status = servo_lib.get(dut_control)
  dut_on, dut_off, programmer = _GetFlashromInfo(board, servo_status)

  with file_utils.UnopenedTemporaryFile() as tmp_file, _HandleDutControl(
      dut_on, dut_off, dut_control):
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
