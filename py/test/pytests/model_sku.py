# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A test to confirm and set SKU information.

Description
-----------
A test to confirm SKU information, then apply SKU or model specific settings.
And there are two modes:

1. manually ask to operator to confirm SKU information.
2. automatically compare SKU information with device data - component.sku.

If device data - component.sku is set then this test will go to automatic mode
or manual mode will be executed.

This is a test to verify hardware root of trust, so there's no options to
set auto verification for this test. Instead, either it relies on the operator
to check manually or compares with device data from shopfloor which would need
to be configured in advance.

After the SKU is confirmed, the test will load a JSON configuration specified by
``config_name``. The config should be a dictionary containing what device data
(usually ``component.*``) to set for matched model and SKU. For example, to set
if the touchscreen is available for model 'coral' with default True, and only
False for product_name `Coral` SKU 3::

  {
    "model": {
      "coral": {
        "component.has_touchscreen": true
      }
    },
    "product_sku": {
      "Coral": {
        "3": {
          "component.has_touchscreen": false
        }
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

Examples
--------
To ask OP to confirm sku information, add this in test list::

  {
    "pytest_name": "model_sku"
  }
"""

import logging

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
_PRODUCT_NAME_PATH = '/sys/devices/virtual/dmi/id/product_name'

_MOSYS_ARGS = ['model', 'sku', 'chassis', 'brand']


class PlatformSKUModelTest(test_case.TestCase):
  """A test to confirm and set SKU and model information."""

  ARGS = [
      Arg('config_name', basestring,
          'Name of JSON config to load for setting device data.', default=None),
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._config = config_utils.LoadConfig(config_name=self.args.config_name)
    self._platform = {}

  def ApplyConfig(self):
    model = self._platform.get('model', '')
    product_name = self._dut.ReadFile(_PRODUCT_NAME_PATH).strip()
    sku = self._platform.get('sku', '')
    model_config = self._config.get('model', {}).get(model, {})
    if 'product_sku' in self._config:
      sku_config = self._config.get(
          'product_sku', {}).get(product_name, {}).get(sku, {})
    else:
      # TODO(chuntsen): Remove getting config from 'sku' after a period of time.
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
          i, 1,
          self._platform[arg] if self._platform[arg] is not None else 'N/A')

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

  def runTest(self):
    self.GetPlatformData()

    if self.CheckByDeviceData():
      return

    self.CheckByOperator()
