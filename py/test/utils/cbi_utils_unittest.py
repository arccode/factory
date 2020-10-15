#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import subprocess
import unittest
from unittest import mock

from cros.factory.test.utils import cbi_utils


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
    mock_popen = mock.MagicMock()
    mock_process = mock.MagicMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = None, None
    self.dut.Popen = mock_popen
    mock_popen.return_value = mock_process
    cbi_utils.SetCbiData(self.dut, 'SKU_ID', 1)
    mock_popen.assert_called_once_with(
        command=['ectool', 'cbi', 'set', '2', '1', '4'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

  def testSetFail(self):
    mock_popen = mock.MagicMock()
    mock_process = mock.MagicMock()
    mock_process.returncode = 1
    mock_process.communicate.return_value = None, None
    self.dut.Popen = mock_popen
    mock_popen.return_value = mock_process
    self.assertRaises(cbi_utils.CbiException,
                      cbi_utils.SetCbiData, self.dut, 'SKU_ID', 1)
    mock_popen.assert_called_once_with(
        command=['ectool', 'cbi', 'set', '2', '1', '4'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)


if __name__ == '__main__':
  unittest.main()
