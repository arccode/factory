# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A test to update CBI data to EEPROM.

Description
-----------
A test to set CBI data from device data to EEPROM by using ``ectool cbi``.
Available device data are `component.sku`, `component.dram_part_num` and
`component.pcb_supplier`. When updating the SKU ID, if the FW Config can be
queried from the cros_config, then the FW Config will be updated as well.
If you want to run the pytest `model_sku` with the SKU ID set by this pytest,
you need to reboot the DUT first.

Test Procedure
--------------
This is an automatic test that doesn't need any user interaction.

Dependency
----------
- ``ectool`` utility.
- ``cros_config_mock`` utility.

Examples
--------
To set SKU_ID, DRAM_PART_NUM and PCB_SUPPLIER from device data to CBI, add
this in test list::

  {
    "pytest_name": "update_cbi",
    "args": {
      "cbi_data_names": ['SKU_ID', 'DRAM_PART_NUM', 'PCB_SUPPLIER']
    }
  }

To set SKU ID and run the pytest `model_sku`, add this in test list::

  {
    "subtests": [
      {
        "pytest_name": "update_cbi",
        "args": {
          "cbi_data_names": ['SKU_ID']
        }
      },
      "FullRebootStep",
      {
        "pytest_name": "model_sku"
      }
    ]
  }
"""

import logging

from cros.factory.device import device_utils
from cros.factory.test.utils.cbi_utils import CbiDataName
from cros.factory.test.utils.cbi_utils import GetCbiData
from cros.factory.test.utils.cbi_utils import SetCbiData
from cros.factory.test import device_data
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils.schema import JSONSchemaDict


_DEFAULT_SKU_ID = 0x7fffffff
_KEY_COMPONENT_SKU = device_data.JoinKeys(
    device_data.KEY_COMPONENT, 'sku')
_KEY_COMPONENT_DRAM_PART_NUM = device_data.JoinKeys(
    device_data.KEY_COMPONENT, 'dram_part_num')
_KEY_COMPONENT_PCB_SUPPLIER = device_data.JoinKeys(
    device_data.KEY_COMPONENT, 'pcb_supplier')

_ARG_CBI_DATA_NAMES_SCHEMA = JSONSchemaDict(
    'cbi_data_names schema object', {
        'type': 'array',
        'items': {
            'enum': [
                CbiDataName.SKU_ID,
                CbiDataName.DRAM_PART_NUM,
                CbiDataName.PCB_SUPPLIER
            ]
        }
    })


class UpdateCBITest(test_case.TestCase):
  """A test to set CBI fields from device data to EEPROM."""
  ARGS = [
      Arg('cbi_data_names', list, 'List of CBI data names to update',
          schema=_ARG_CBI_DATA_NAMES_SCHEMA)]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()

  def GetCrosConfigData(self, sku_id, path, name, return_type):
    output = self._dut.CallOutput(
        ['cros_config_mock', '--sku-id', str(sku_id), path, name])
    if output:
      return return_type(output.strip())
    logging.warning("Can't get %s/%s from cros_config_mock", path, name)
    return None

  def GetFirmwareConfigFromCrosConfig(self, sku_id):
    return self.GetCrosConfigData(sku_id, '/firmware', 'firmware-config', int)

  def GetDeviceData(self, key, data_type):
    assert data_type in (int, str), 'data_type should be either int or str.'
    value = device_data.GetDeviceData(key)
    if value is None:
      self.FailTask('No device data (%s)' % key)
      return None
    if data_type == str:
      return str(value)
    elif isinstance(value, int):
      return value
    elif isinstance(value, str):
      # This can convert both 10-based and 16-based starting with '0x'.
      return int(value, 0)
    self.FailTask('The value in device-data is not an integer nor a '
                  'string representing an integer literal in radix base.')
    return None

  def CheckCbiData(self, data_name, expected_data):
    read_data = GetCbiData(self._dut, data_name)
    if read_data != expected_data:
      self.FailTask('The data_name=%d in EEPROM (%d) is not equal to the '
                    'data in device data (%d) after we set.' %
                    (data_name, read_data, expected_data))

  def SetSKUID(self):
    old_sku_id = GetCbiData(self._dut, CbiDataName.SKU_ID)
    new_sku_id = self.GetDeviceData(_KEY_COMPONENT_SKU, int)
    if old_sku_id is None:
      self.FailTask('No valid SKU ID found in EEPROM.')

    if old_sku_id == new_sku_id:
      return

    if new_sku_id > 2 ** 32 - 1:
      self.FailTask('SKU ID (%d) should not be greater than UINT32_MAX (%d).' %
                    (new_sku_id, 2 ** 32 - 1))

    old_fw_config = GetCbiData(self._dut, CbiDataName.FW_CONFIG)
    new_fw_config = self.GetFirmwareConfigFromCrosConfig(new_sku_id)

    if old_fw_config is None and new_fw_config is None:
      logging.info('FW CONFIG is not supported on this board.')
    elif new_fw_config is None:
      self.FailTask('FW_CONFIG does not exist in cros_config but is '
                    'set in EEPROM.')
    elif old_fw_config and old_fw_config != new_fw_config \
        and old_sku_id != _DEFAULT_SKU_ID:
      # The fw_config is allowed to be any value while the board is
      # unprovisioned, otherwise the fw_config value must match what
      # configuration says it should be based on the SKU value
      self.FailTask('FW CONFIG in EEPROM (%d) is not equal to the '
                    'FW CONFIG in cros_config (%d).' %
                    (old_fw_config, new_fw_config))

    session.console.info('Set the new SKU_ID to EEPROM (%r -> %r).',
                         old_sku_id, new_sku_id)
    SetCbiData(self._dut, CbiDataName.SKU_ID, new_sku_id)
    self.CheckCbiData(CbiDataName.SKU_ID, new_sku_id)

    if new_fw_config is not None:
      session.console.info('Set the new FW_CONFIG to EEPROM (%r -> %r).',
                           old_fw_config, new_fw_config)
      SetCbiData(self._dut, CbiDataName.FW_CONFIG, new_fw_config)
      self.CheckCbiData(CbiDataName.FW_CONFIG, new_fw_config)

  def SetDramPartNum(self):
    old_dram_part_num = GetCbiData(self._dut, CbiDataName.DRAM_PART_NUM)
    new_dram_part_num = self.GetDeviceData(_KEY_COMPONENT_DRAM_PART_NUM, str)

    if old_dram_part_num == new_dram_part_num:
      return

    session.console.info('Set the new DRAM_PART_NUM to EEPROM (%r -> %r).',
                         old_dram_part_num, new_dram_part_num)
    SetCbiData(self._dut, CbiDataName.DRAM_PART_NUM, new_dram_part_num)
    self.CheckCbiData(CbiDataName.DRAM_PART_NUM, new_dram_part_num)

  def SetPcbSupplier(self):
    old_pcb_supplier = GetCbiData(self._dut, CbiDataName.PCB_SUPPLIER)
    new_pcb_supplier = self.GetDeviceData(_KEY_COMPONENT_PCB_SUPPLIER, int)

    if old_pcb_supplier == new_pcb_supplier:
      return

    session.console.info('Set the new PCB_SUPPLIER to EEPROM (%r -> %r).',
                         old_pcb_supplier, new_pcb_supplier)
    SetCbiData(self._dut, CbiDataName.PCB_SUPPLIER, new_pcb_supplier)
    self.CheckCbiData(CbiDataName.PCB_SUPPLIER, new_pcb_supplier)

  def runTest(self):
    if CbiDataName.SKU_ID in self.args.cbi_data_names:
      self.SetSKUID()
    if CbiDataName.DRAM_PART_NUM in self.args.cbi_data_names:
      self.SetDramPartNum()
    if CbiDataName.PCB_SUPPLIER in self.args.cbi_data_names:
      self.SetPcbSupplier()