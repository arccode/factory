# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A test to update SKU ID to EEPROM.

Description
-----------
A test to set SKU ID from device data ``component.sku`` to EEPROM by using
``ectool cbi``.  If you want to run the pytest `model_sku` with the SKU ID set
by this pytest, you need to reboot the DUT first.

Test Procedure
--------------
This is an automatic test that doesn't need any user interaction.

Dependency
----------
- ``ectool`` utility.

Examples
--------
To set SKU ID from device data to EEPROM, add this in test list::

  {
    "pytest_name": "update_sku"
  }

To set SKU ID and run the pytest `model_sku`, add this in test list::

  {
    "subtests": [
      {
        "pytest_name": "update_sku"
      },
      "FullRebootStep",
      {
        "pytest_name": "model_sku"
      }
    ]
  }
"""

import logging
import re
import subprocess

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import device_data
from cros.factory.test import session
from cros.factory.test import test_case


_KEY_COMPONENT_SKU = device_data.JoinKeys(device_data.KEY_COMPONENT, 'sku')


class UpdateSKUIDTest(test_case.TestCase):
  """A test to set SKU ID from device data to EEPROM."""

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()

  def SetToEEPROM(self):
    OEM_ID_TYPE = 1
    SKU_ID_TYPE = 2

    def GetDataFromEEPROM(data_type):
      # Usage: ectool cbi get <type> [get_flag]
      # <type> is one of 0: BOARD_VERSION, 1: OEM_ID, 2: SKU_ID
      cbi_output = self._dut.CallOutput(
          ['ectool', 'cbi', 'get', str(data_type)])
      if cbi_output:
        # If the CBI field to be probed is set, the output from
        # 'ectool cbi get' is 'As integer: %u (0x%x)\n' % (val, val)
        match = re.search(r'As integer: ([0-9]+) \(0x[0-9a-fA-F]+\)',
                          cbi_output)
        if match:
          return int(match.group(1))
        else:
          self.FailTask('Is the format of the output from "ectool cbi get" '
                        'changed?')
      else:
        logging.warning('CBI field %d is not found in EEPROM.', data_type)
        return None

    def GetSKUIDFromDeviceData():
      device_data_sku = device_data.GetDeviceData(_KEY_COMPONENT_SKU)
      if device_data_sku is None:
        self.FailTask('No SKU ID in device data (%s)' % _KEY_COMPONENT_SKU)
      elif isinstance(device_data_sku, int):
        return device_data_sku
      elif isinstance(device_data_sku, basestring):
        # This can covert both 10-based and 16-based starting with '0x'.
        return int(device_data_sku, 0)
      else:
        self.FailTask('The SKU ID in device-data is not an integer nor a '
                      'string representing an integer literal in radix base.')

    def GetOEMIDFromCrosConfig(sku_id):
      output = self._dut.CallOutput(
          ['cros_config', '--test_sku_id=%d' % sku_id, '/', 'oem-id'])
      if output:
        return int(output.strip())
      else:
        logging.warning('Can\'t get OEM ID from cros_config')
        return None

    new_sku_id = GetSKUIDFromDeviceData()
    old_sku_id = GetDataFromEEPROM(SKU_ID_TYPE)
    if old_sku_id is None:
      self.FailTask('No valid SKU ID found in EEPROM')

    if old_sku_id == new_sku_id:
      return

    if new_sku_id > 2 ** 32 - 1:
      self.FailTask('SKU ID (%d) should not be greater than UINT32_MAX (%d)' %
                    (new_sku_id, 2 ** 32 - 1))
    # The data size should be 1, 2 or 4.  See
    # https://chromium.googlesource.com/chromiumos/platform/ec/+/master/util/cbi-util.c#140
    if new_sku_id <= 2 ** 8 - 1:
      data_size = 1
    elif new_sku_id <= 2 ** 16 - 1:
      data_size = 2
    else:
      data_size = 4

    oem_id_in_eeprom = GetDataFromEEPROM(OEM_ID_TYPE)
    oem_id_in_cros_config = GetOEMIDFromCrosConfig(new_sku_id)

    if oem_id_in_eeprom is None and oem_id_in_cros_config is None:
      logging.info('OEM ID is not supported on this board.')
    elif oem_id_in_eeprom is None:
      self.FailTask('OEM ID is not set in EEPROM but exists in cros_config.')
    elif oem_id_in_cros_config is None:
      self.FailTask('OEM ID does not exist in cros_config but is set in'
                    'EEPROM.')
    elif oem_id_in_eeprom != oem_id_in_cros_config:
      self.FailTask('OEM ID in EEPROM (%d) is not equal to the OEM ID in '
                    'cros_config (%d)' % (oem_id_in_eeprom,
                                          oem_id_in_cros_config))

    logging.info('Set the new SKU_ID to EEPROM (%d -> %d)',
                 old_sku_id, new_sku_id)
    # Usage: ectool cbi set <type> <value> <size> [set_flag]
    # <type> is one of 0: BOARD_VERSION, 1: OEM_ID, 2: SKU_ID
    # <value> is integer to be set. No raw data support yet.
    # <size> is the size of the data.
    command = ['ectool', 'cbi', 'set', str(SKU_ID_TYPE), str(new_sku_id),
               str(data_size)]
    process = self._dut.Popen(
        command=command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    session.console.info('%s: stdout: %s\n', command, stdout)
    if process.returncode != 0:
      session.console.error('returncode: %d, stderr: %s',
                            process.returncode, stderr)
      self.FailTask('Failed to set SKU ID to EEPROM. returncode=%d, stdout=%s, '
                    'stderr=%s' % (process.returncode, stdout, stderr))


    check_sku_id = GetDataFromEEPROM(SKU_ID_TYPE)
    if check_sku_id != new_sku_id:
      self.FailTask('The SKU ID in EEPROM (%d) is not equal to the SKU ID in '
                    'device data (%d) after we set' %
                    (check_sku_id, new_sku_id))

  def runTest(self):
    self.SetToEEPROM()
