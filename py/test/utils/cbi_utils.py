# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A wrapper for getting/setting CBI values.

This module provides functions to set and get CBI values using data names
(e.g. OEM_ID) instead of data tags (e.g. 1).
"""

import collections
import logging
import re
import subprocess

from cros.factory.utils import type_utils


class CbiException(Exception):
  """CBI exception class."""


# Usage: ectool cbi get <tag> [get_flag]
# Usage: ectool cbi set <tag> <value/string> <size> [set_flag]
#   <tag> is one of:
#     0: BOARD_VERSION
#     1: OEM_ID
#     2: SKU_ID
#     3: DRAM_PART_NUM
#     4: OEM_NAME
#     5: MODEL_ID
#     6: FW_CONFIG
#     7: PCB_SUPPLIER
#   <value/string> is an integer or a string to be set.
#   <size> is the size of the data in byte. It should be zero for
#     string types.
CbiDataName = type_utils.Enum([
    'BOARD_VERSION',
    'OEM_ID',
    'SKU_ID',
    'DRAM_PART_NUM',
    'OEM_NAME',
    'MODEL_ID',
    'FW_CONFIG',
    'PCB_SUPPLIER'])
CbiDataAttr = collections.namedtuple('DataAttr', ['tag', 'type', 'size'])
CbiDataDict = {
    CbiDataName.BOARD_VERSION: CbiDataAttr(0, int, 1),
    CbiDataName.OEM_ID: CbiDataAttr(1, int, 1),
    CbiDataName.SKU_ID: CbiDataAttr(2, int, 4),
    CbiDataName.DRAM_PART_NUM: CbiDataAttr(3, str, 0),
    CbiDataName.OEM_NAME: CbiDataAttr(4, str, 0),
    CbiDataName.MODEL_ID: CbiDataAttr(5, int, 1),
    CbiDataName.FW_CONFIG: CbiDataAttr(6, int, 4),
    CbiDataName.PCB_SUPPLIER: CbiDataAttr(7, int, 1)
}
CbiEepromWpStatus = type_utils.Enum(['Locked', 'Unlocked', 'Absent'])
WpErrorMessages = ('Write-protect is enabled or EC explicitly '
                   'refused to change the requested field.')


def GetCbiData(dut, data_name):
  if data_name not in CbiDataName:
    raise CbiException('%s is not a valid CBI data name.' % data_name)
  data_attr = CbiDataDict[data_name]

  cbi_output = dut.CallOutput(
      ['ectool', 'cbi', 'get', str(data_attr.tag)])
  if cbi_output:
    # If the CBI field to be probed is set, the output from
    # 'ectool cbi get' is 'As uint: %u (0x%x)\n' % (val, val)
    if data_attr.type == int:
      match = re.search(r'As uint: ([0-9]+) \(0x[0-9a-fA-F]+\)',
                        cbi_output)
      if match:
        return int(match.group(1))
      raise CbiException('Is the format of the output from "ectool cbi get" '
                         'changed?')
    return cbi_output.strip()
  logging.warning('CBI field %s is not found in EEPROM.', data_name)
  return None


def SetCbiData(dut, data_name, value):
  if data_name not in CbiDataName:
    raise CbiException('%s is not a valid CBI data name.' % data_name)
  data_attr = CbiDataDict[data_name]
  if not isinstance(value, data_attr.type):
    raise CbiException('value %r should have type %r.' %
                       (value, data_attr.type))

  command = ['ectool', 'cbi', 'set', str(data_attr.tag), str(value),
             str(data_attr.size)]
  process = dut.Popen(
      command=command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  stdout, stderr = process.communicate()
  logging.info('%s: stdout: %s\n', command, stdout)
  if process.returncode != 0:
    logging.error('returncode: %d, stderr: %s',
                  process.returncode, stderr)
    raise CbiException('Failed to set data_name=%s to EEPROM. '
                       'returncode=%d, stdout=%s, stderr=%s' %
                       (data_name, process.returncode, stdout, stderr))


def CheckCbiEepromPresent(dut):
  """Check that the CBI EEPROM chip is present.

  Args:
    dut: The SystemInterface of the device.

  Returns:
    True if the CBI EEPROM chip is present otherwise False.
  """
  CBI_EEPROM_EC_CHIP_TYPE = 0
  CBI_EEPROM_EC_CHIP_INDEX = 0
  command = [
      'ectool', 'locatechip',
      str(CBI_EEPROM_EC_CHIP_TYPE),
      str(CBI_EEPROM_EC_CHIP_INDEX)
  ]
  process = dut.Popen(command=command, stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE)
  stdout, stderr = process.communicate()
  logging.debug('command=%r, returncode=%d, stdout=%r, stderr=%r', command,
                process.returncode, stdout, stderr)
  return process.returncode == 0


def VerifyCbiEepromWpStatus(dut, cbi_eeprom_wp_status):
  """Verify CBI EEPROM status.

  If cbi_eeprom_wp_status is Absent, CBI EEPROM must be absent. If
  cbi_eeprom_wp_status is Locked, write protection must be on. Otherwise, write
  protection must be off.

  Args:
    dut: The SystemInterface of the device.
    cbi_eeprom_wp_status: The expected status, must be one of CbiEepromWpStatus.

  Raises:
    CbiException if the status is not expected, GetCbiData fails when CBI is
    expected to be present, or SetCbiData fails when CBI is expected to be
    unlocked.
  """
  detect_presence = CheckCbiEepromPresent(dut)
  expected_presence = cbi_eeprom_wp_status != CbiEepromWpStatus.Absent
  if detect_presence != expected_presence:
    raise CbiException(('CheckCbiEepromPresent returns %r but is expected to be'
                        ' %r.' % (detect_presence, expected_presence)))
  if not detect_presence:
    return

  def _GetSKUId():
    result = GetCbiData(dut, CbiDataName.SKU_ID)
    if result is None:
      raise CbiException('GetCbiData fails.')
    return result

  def _SetSKUId(value):
    try:
      SetCbiData(dut, CbiDataName.SKU_ID, value)
    except CbiException as e:
      return False, str(e)
    else:
      return True, None

  sku_id = _GetSKUId()
  # The allowed range of sku id is [0, 0x7FFFFFFF].
  test_sku_id = (sku_id + 1) % 0x80000000

  write_success, messages = _SetSKUId(test_sku_id)
  sku_id_afterward = _GetSKUId()
  detect_write_protect = sku_id == sku_id_afterward
  expected_write_protect = cbi_eeprom_wp_status == CbiEepromWpStatus.Locked
  errors = []
  if expected_write_protect:
    if write_success:
      errors.append('_SetSKUId should return False but get True.')
    elif WpErrorMessages not in messages:
      errors.append('Output of _SetSKUId should contain %r but get %r' %
                    (WpErrorMessages, messages))
  else:
    if not write_success:
      errors.append('_SetSKUId should return True but get False.')

  if detect_write_protect:
    if not expected_write_protect:
      errors.append('_SetSKUId should write the CBI EEPROM but it does not.')
  else:
    if expected_write_protect:
      errors.append('_SetSKUId should not write the CBI EEPROM but it does.')
    write_success, unused_messages = _SetSKUId(sku_id)
    if not write_success:
      errors.append('_SetSKUId fails.')
  if errors:
    errors.append('write protection switch of CBI EEPROM is%s enabled.' %
                  (' not' if expected_write_protect else ''))
    raise CbiException(' '.join(errors))
