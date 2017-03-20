# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""An E2E test to test the scan factory test."""

import factory_common  # pylint: disable=unused-import
from cros.factory.test.e2e_test import e2e_test
from cros.factory.test import shopfloor


class ScanE2ETest(e2e_test.E2ETest):
  """The scan E2E test."""
  pytest_name = 'scan'
  dargs = dict(
      label='Serial Number',
      device_data_key='serial_number',
      regexp='^[A-Z0-9]{5}$')

  @e2e_test.E2ETestCase()
  def testCorrectSerialNumber(self):
    self.uictl.WaitForContent(
        search_text='Please scan the Serial Number and press ENTER')

    serial_number = '12345'
    self.uictl.SetElementValue('scan-value', serial_number)
    self.uictl.PressKey(self.uictl.KEY_ENTER)

    self.WaitForPass()
    self.assertEquals(shopfloor.GetDeviceData()['serial_number'],
                      serial_number)

  @e2e_test.E2ETestCase()
  def testIncorrectSerialNumber(self):
    self.uictl.WaitForContent(
        search_text='Please scan the Serial Number and press ENTER')

    self.uictl.SetElementValue('scan-value', '@#$%^')
    self.uictl.PressKey(self.uictl.KEY_ENTER)

    self.uictl.WaitForContent(
        element_id='scan-status', search_text='does not match')
