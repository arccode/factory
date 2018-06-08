# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A test to confirm and set SKU information.

Description
-----------
This test performs the following tasks,

1. If ``set_sku_id`` is True, set SKU ID from device data to EEPROM.
2. Confirm SKU information and apply SKU or model specific settings, and there
   are two modes:

  - automatically compare SKU information with device data ``component.sku``.
  - manually ask to operator to confirm SKU information.

If ``set_sku_id`` is True, then device data ``component.sku`` must be set then
this test will set the SKU ID to EEPROM by using ectool cbi.

If device data ``component.sku`` is set then this test will go to automatic mode
or manual mode will be executed.

This is a test to verify hardware root of trust when ``set_sku_id`` is False.
There's no options to set auto verification for this test. Instead, either it
relies on the operator to check manually or compares with device data from
shopfloor which would need to be configured in advance.

After the SKU is confirmed, the test will load a JSON configuration specified by
``config_name``. The config should be a dictionary containing what device data
(usually ``component.*``) to set for matched model and SKU. For example, to set
if the touchscreen is available for model 'coral' with default True, and only
False for SKU 3::

  {
    "model": {
      "coral": {
        "component.has_touchscreen": true
      }
    },
    "sku": {
      "3": {
        "component.has_touchscreen": false
      }
    }
  }

Test Procedure
--------------
The test runs following commands:

- mosys platform model
- mosys platform sku
- mosys platform chassis
- mosys platform brand

And then asks OP to press ENTER/ESC to confirm if these values are correct.

Dependency
----------
- ``mosys`` utility.
- ``ectool`` utility.

Examples
--------
To ask OP to confirm sku information, add this in test list::

  {
    "pytest_name": "model_sku"
  }

To set device data ``component.sku`` to EEPROM, add this in test list::

  {
    "pytest_name": "model_sku",
    "args": {
      "set_sku_id": true
    }
  }
"""

import logging
import re

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import device_data
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.i18n import _
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import config_utils


_KEY_COMPONENT_SKU = device_data.JoinKeys(device_data.KEY_COMPONENT, 'sku')

_MOSYS_ARGS = ['model', 'sku', 'chassis', 'brand']


class PlatformSKUModelTest(test_case.TestCase):
  """A test to confirm and set SKU and model information."""

  ARGS = [
      Arg('config_name', basestring,
          'Name of JSON config to load for setting device data.', default=None),
      Arg('set_sku_id', bool,
          'Set the SKU ID in the device data to EEPROM.', default=False),
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._config = config_utils.LoadConfig(config_name=self.args.config_name)
    self._platform = {}

  def ApplyConfig(self):
    model = self._platform.get('model', '')
    sku = self._platform.get('sku', '')
    model_config = self._config.get('model', {}).get(model, {})
    sku_config = self._config.get('sku', {}).get(sku, {})

    config_utils.OverrideConfig(model_config, sku_config)
    if model_config:
      logging.info('Apply model/SKU config: %r', model_config)
      device_data.UpdateDeviceData(model_config)

  def CheckByOperator(self):
    self.ui.SetInstruction(_('Please confirm following values'))

    table = ui_templates.Table(rows=len(_MOSYS_ARGS) + 1, cols=2,
                               element_id='mosys_table')
    table.SetContent(0, 0, '<strong>Key</strong>')
    table.SetContent(0, 1, '<strong>Value</strong>')
    for i, arg in enumerate(_MOSYS_ARGS, 1):
      table.SetContent(i, 0, arg)
      table.SetContent(
          i, 1, self._platform[arg] if self._platform[arg] != None else 'N/A')

    self.ui.SetState([table.GenerateHTML(), test_ui.PASS_FAIL_KEY_LABEL])

    key = self.ui.WaitKeysOnce([test_ui.ENTER_KEY, test_ui.ESCAPE_KEY])
    if key == test_ui.ESCAPE_KEY:
      self.FailTask('Failed by operator')
    self.ApplyConfig()

  def CheckByDeviceData(self):
    value = device_data.GetDeviceData(_KEY_COMPONENT_SKU)
    if value is None:
      return False

    self.assertEqual(
        str(value), self._platform['sku'],
        'Value [%s] from "mosys platform sku" does not match '
        'device data [%s]' % (self._platform['sku'], value))

    self.ApplyConfig()
    return True

  def GetPlatformData(self):
    for arg in _MOSYS_ARGS:
      output = self._dut.CallOutput(['mosys', 'platform', arg])
      if output is not None:
        output = output.strip()
      self._platform[arg] = output


  def SetToEEPROM(self):
    OEM_ID_TYPE = 1
    SKU_ID_TYPE = 2

    def GetSKUIDFromEEPROM():
      # Usage: ectool cbi get <type> [get_flag]
      # <type> is one of 0: BOARD_VERSION, 1: OEM_ID, 2: SKU_ID
      cbi_output = self._dut.CallOutput('ectool cbi get %d', SKU_ID_TYPE)
      # The output from ectool cbi get is 'SKU_ID: %u (0x%x)\n' % (val, val)
      match = re.search(r'SKU_ID: ([0-9]+) \(0x[0-9a-fA-F]+\)', cbi_output)
      if match:
        return int(match.group(1))
      else:
        self.FailTask('Is the format of the output from "ectool cbi get" '
                      'changed?')

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
        self.FailTask('The SKU ID in device-data is not an integer')

    def GetOEMIDFromEEPROM():
      # Usage: ectool cbi get <type> [get_flag]
      # <type> is one of 0: BOARD_VERSION, 1: OEM_ID, 2: SKU_ID
      cbi_output = self._dut.CallOutput('ectool cbi get %d', OEM_ID_TYPE)
      # The output from ectool cbi get is 'OEM_ID: %u (0x%x)\n' % (val, val)
      match = re.search(r'OEM_ID: ([0-9]+) \(0x[0-9a-fA-F]+\)', cbi_output)
      if match:
        return int(match.group(1))
      else:
        self.FailTask('Is the format of the output from "ectool cbi get" '
                      'changed?')

    def GetOEMIDFromCrosConfig(sku_id):
      output = self._dut.CallOutput(
          'cros_config --test_sku_id=%d / oem-id' % sku_id)
      return int(output)

    new_sku_id = GetSKUIDFromDeviceData()
    old_sku_id = GetSKUIDFromEEPROM()
    if old_sku_id == new_sku_id:
      return

    if new_sku_id > 2**32 - 1:
      self.FailTask('SKU ID (%d) should not be greater than UINT32_MAX (%d)' %
                    (new_sku_id, 2**32 - 1))
    # The data size should be 1, 2 or 4.  See
    # https://chromium.googlesource.com/chromiumos/platform/ec/+/master/util/cbi-util.c#140
    if new_sku_id <= 2**8 - 1:
      data_size = 1
    elif new_sku_id <= 2**16 - 1:
      data_size = 2
    else:
      data_size = 4

    oem_id_in_eeprom = GetOEMIDFromEEPROM()
    oem_id_in_cros_config = GetOEMIDFromCrosConfig(new_sku_id)
    if oem_id_in_eeprom != oem_id_in_cros_config:
      self.FailTask('OEM ID in EEPROM (%d) is not equal to the OEM ID in '
                    'cros_config (%d)' % (oem_id_in_eeprom,
                                          oem_id_in_cros_config))

    logging.info('Setting the new SKU_ID to EEPROM (%d -> %d)',
                 old_sku_id, new_sku_id)
    # Usage: ectool cbi set <type> <value> <size> [set_flag]
    # <type> is one of 0: BOARD_VERSION, 1: OEM_ID, 2: SKU_ID
    # <value> is integer to be set. No raw data support yet.
    # <size> is the size of the data.
    self._dut.CheckCall('ectool cbi set %d %s %d' %
                        (SKU_ID_TYPE, new_sku_id, data_size))

  def runTest(self):
    if self.args.set_sku_id:
      self.SetToEEPROM()
    self.GetPlatformData()
    if self.CheckByDeviceData():
      return
    self.CheckByOperator()
