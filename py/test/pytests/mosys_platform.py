# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A test to confirm SKU information.

Description
-----------
A test to ask OP to confirm SKU information manually.

Ths is a test to verify hardware root of trust, so there's no options to
set auto verification for this test.

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
There's no options for this test::

  OperatorTest(pytest_name='mosys_platform')

"""

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.i18n import test_ui as i18n_test_ui


_TABLE_CSS = '''
#mosys_table {
  margin: auto;
  border: 1px solid black;
}

#mosys_table td {
  border: 1px solid black;
  padding-left: 20px;
  padding-right: 20px;
}

#state {
  font-size: 150%;
}
'''


class MosysPlatformTest(unittest.TestCase):
  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._ui = test_ui.UI(css=_TABLE_CSS)
    self._template = ui_templates.TwoSections(self._ui)

  def runTest(self):
    self._template.SetInstruction(
        i18n_test_ui.MakeI18nLabel('Please confirm following values'))

    self._ui.BindKey(test_ui.ENTER_KEY, lambda _: self._ui.Pass())
    self._ui.BindKey(test_ui.ESCAPE_KEY,
                     lambda _: self._ui.Fail('Failed by operator'))

    mosys_args = ['model', 'sku', 'chassis', 'brand']
    table = ui_templates.Table(rows=len(mosys_args) + 1, cols=2,
                               element_id='mosys_table')
    table.SetContent(0, 0, '<strong>Key</strong>')
    table.SetContent(0, 1, '<strong>Value</strong>')
    for i, arg in enumerate(mosys_args, 1):
      output = self._dut.CallOutput(['mosys', 'platform', arg])
      if output is None:
        output = 'N/A'

      table.SetContent(i, 0, arg)
      table.SetContent(i, 1, output)

    self._template.SetState(
        table.GenerateHTML() + '<br/>' + test_ui.MakePassFailKeyLabel())

    self._ui.Run()

