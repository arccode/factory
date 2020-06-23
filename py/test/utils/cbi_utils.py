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
  pass


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
