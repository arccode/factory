#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import subprocess
import unittest
from unittest import mock

from cros.factory.test.utils import cbi_utils


def _CreatePopenMock(returncode, stdout=None, stderr=None):
  mock_popen = mock.MagicMock()
  mock_process = mock.MagicMock()
  mock_process.returncode = returncode
  mock_process.communicate.return_value = stdout, stderr
  mock_popen.return_value = mock_process
  return mock_popen


def _SetMockStatus(wp_status, present_mock, get_cbi_mock, set_cbi_mock,
                   error_messages):
  present_mock.reset_mock()
  get_cbi_mock.reset_mock()
  set_cbi_mock.reset_mock()
  if wp_status == cbi_utils.CbiEepromWpStatus.Absent:
    present_mock.return_value = False
  elif wp_status == cbi_utils.CbiEepromWpStatus.Locked:
    present_mock.return_value = True
    get_cbi_mock.side_effect = [54321, 54321]
    set_cbi_mock.side_effect = cbi_utils.CbiException(error_messages)
  else:
    present_mock.return_value = True
    get_cbi_mock.side_effect = [54321, 54322]
    set_cbi_mock.side_effect = [None, None]


class CbiUtilsTest(unittest.TestCase):

  def setUp(self):
    self.dut = mock.MagicMock()

  def testWrongDataName(self):
    self.assertRaises(cbi_utils.CbiException,
                      cbi_utils.GetCbiData, self.dut, 'WRONG_NAME')

  def testGetStr(self):
    oem_name = 'oem-name'
    self.dut.CallOutput.return_value = oem_name
    self.assertEqual(oem_name, cbi_utils.GetCbiData(self.dut, 'OEM_NAME'))

  def testGetInt(self):
    oem_id = ('As uint: 3 (0x3)\n'
              'As binary: 03\n')
    self.dut.CallOutput.return_value = oem_id
    self.assertEqual(3, cbi_utils.GetCbiData(self.dut, 'OEM_ID'))

  def testGetWrongType(self):
    # In case the format of `ectool cbi get` changes.
    oem_id = '3'
    self.dut.CallOutput.return_value = oem_id
    self.assertRaises(cbi_utils.CbiException,
                      cbi_utils.GetCbiData, self.dut, 'OEM_ID')

  def testGetEmpty(self):
    oem_id = ''
    self.dut.CallOutput.return_value = oem_id
    self.assertEqual(None, cbi_utils.GetCbiData(self.dut, 'OEM_ID'))

  def testGetNone(self):
    oem_id = None
    self.dut.CallOutput.return_value = oem_id
    self.assertEqual(None, cbi_utils.GetCbiData(self.dut, 'OEM_ID'))

  def testSetWrongDataName(self):
    self.assertRaises(cbi_utils.CbiException,
                      cbi_utils.SetCbiData, self.dut, 'WRONG_NAME', 0)

  def testSetWrongValueType(self):
    self.assertRaises(cbi_utils.CbiException,
                      cbi_utils.SetCbiData, self.dut, 'OEM_NAME', 0)

  def testSetSuccess(self):
    self.dut.Popen = _CreatePopenMock(0)
    cbi_utils.SetCbiData(self.dut, 'SKU_ID', 1)
    self.dut.Popen.assert_called_once_with(
        command=['ectool', 'cbi', 'set', '2', '1', '4'], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

  def testSetFail(self):
    self.dut.Popen = _CreatePopenMock(1)
    self.assertRaises(cbi_utils.CbiException,
                      cbi_utils.SetCbiData, self.dut, 'SKU_ID', 1)
    self.dut.Popen.assert_called_once_with(
        command=['ectool', 'cbi', 'set', '2', '1', '4'], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

  def testProbePresent(self):
    self.dut.Popen = _CreatePopenMock(0)
    self.assertEqual(cbi_utils.CheckCbiEepromPresent(self.dut), True)
    self.dut.Popen.assert_called_once_with(
        command=['ectool', 'locatechip', '0', '0'], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

  def testProbeAbsent(self):
    self.dut.Popen = _CreatePopenMock(10, 'fake stdout', 'fake stderr')
    self.assertEqual(cbi_utils.CheckCbiEepromPresent(self.dut), False)
    self.dut.Popen.assert_called_once_with(
        command=['ectool', 'locatechip', '0', '0'], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

  @mock.patch(cbi_utils.__name__ + '.SetCbiData')
  @mock.patch(cbi_utils.__name__ + '.GetCbiData')
  @mock.patch(cbi_utils.__name__ + '.CheckCbiEepromPresent')
  def testVerifyWpStatus(self, present_mock, get_cbi_mock, set_cbi_mock):
    for expected_wp_status in cbi_utils.CbiEepromWpStatus:
      for actual_wp_status in cbi_utils.CbiEepromWpStatus:
        for ec_bypass in [False, True]:
          possible_error_messages = []
          if actual_wp_status == cbi_utils.CbiEepromWpStatus.Locked:
            possible_error_messages += cbi_utils.WpErrorMessages
          if ec_bypass:
            possible_error_messages += cbi_utils.WpGeneralErrorMessages
          for error_messages in possible_error_messages:
            _SetMockStatus(actual_wp_status, present_mock, get_cbi_mock,
                           set_cbi_mock, error_messages)
            if expected_wp_status == actual_wp_status:
              cbi_utils.VerifyCbiEepromWpStatus(self.dut, expected_wp_status,
                                                ec_bypass)
            else:
              self.assertRaises(cbi_utils.CbiException,
                                cbi_utils.VerifyCbiEepromWpStatus, self.dut,
                                expected_wp_status, ec_bypass)


if __name__ == '__main__':
  unittest.main()
