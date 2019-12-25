# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

# pylint: disable=no-name-in-module
from cros.factory.probe_info_service.app_engine import probe_tool_manager
from cros.factory.probe_info_service.app_engine import stubby_pb2


class ProbeToolManagerTest(unittest.TestCase):
  _GENERIC_STORAGE_FUNC_NAME = 'generic_storage'

  def setUp(self):
    self._probe_tool_manager = probe_tool_manager.ProbeToolManager()

  def testGetProbeSchema(self):
    # Only to verify if the function returns normally.
    self.assertIsInstance(self._probe_tool_manager.GetProbeSchema(),
                          stubby_pb2.ProbeSchema)

  def testValidateProbeInfoAndGenerateProbeStatementInvalidProbeFunction(self):
    with self.assertRaises(ValueError):
      self._probe_tool_manager.ValidateProbeInfo('no_such_probe_function', [])
    with self.assertRaises(ValueError):
      self._probe_tool_manager.GenerateProbeStatement(
          'no_such_probe_function', [], "comp_name")

  def testValidateProbeInfoAndGenericProbeStatementMissingSomeParameters(self):
    probe_params = self._GenerateEmptyProbeParametersForStorage()
    del probe_params['prv']
    with self.assertRaises(ValueError):
      self._probe_tool_manager.ValidateProbeInfo(
          self._GENERIC_STORAGE_FUNC_NAME, probe_params.values())
    with self.assertRaises(ValueError):
      self._probe_tool_manager.GenerateProbeStatement(
          self._GENERIC_STORAGE_FUNC_NAME, probe_params.values(), "comp_name")

  def testValidateProbeInfoAndGenericProbeStatementMissingHWIntrfParams(self):
    probe_params = self._GenerateEmptyProbeParametersForStorage()
    ret = self._probe_tool_manager.ValidateProbeInfo(
        self._GENERIC_STORAGE_FUNC_NAME, probe_params.values())
    self.assertFalse(ret.is_passed)

    ret = self._probe_tool_manager.GenerateProbeStatement(
        self._GENERIC_STORAGE_FUNC_NAME, probe_params.values(), "comp_name")
    self.assertFalse(ret.is_passed)

  def testValidateProbeInfoAndGenericProbeStatementFormatError(self):
    probe_params = self._GenerateEmptyProbeParametersForStorage()
    probe_params['manfid'].str_value = '0F'
    probe_params['oemid'].str_value = '09AF'
    probe_params['name'].str_value = 'x23456'

    def _CheckResult(result):
      self.assertFalse(result.is_passed)
      self.assertEqual(len(result.probe_parameter_errors), 1)
      self.assertEqual(result.probe_parameter_errors[0].probe_parameter,
                       probe_params['prv'])

    for invalid_prv_value in 'Ay', '':  # Should be a 2-digit hex number.
      probe_params['prv'].str_value = invalid_prv_value
      ret = self._probe_tool_manager.ValidateProbeInfo(
          self._GENERIC_STORAGE_FUNC_NAME, list(probe_params.values()))
      _CheckResult(ret)

      ret = self._probe_tool_manager.GenerateProbeStatement(
          self._GENERIC_STORAGE_FUNC_NAME, list(probe_params.values()),
          "comp_name")
      _CheckResult(ret)

  def testValidateProbeInfoAndGenericProbeStatementAllValueCorrect(self):
    probe_params = self._GenerateEmptyProbeParametersForStorage()
    probe_params['manfid'].str_value = '0F'
    probe_params['oemid'].str_value = '09AF'
    probe_params['name'].str_value = 'x23456'
    probe_params['prv'].str_value = 'AB'
    ret = self._probe_tool_manager.ValidateProbeInfo(
        self._GENERIC_STORAGE_FUNC_NAME, list(probe_params.values()))
    self.assertTrue(ret.is_passed)
    ret = self._probe_tool_manager.GenerateProbeStatement(
        self._GENERIC_STORAGE_FUNC_NAME, list(probe_params.values()),
        "comp_name")
    self.assertTrue(ret.is_passed)

    probe_params['pci_vendor'].str_value = '18BE'
    probe_params['pci_device'].str_value = '1234'
    probe_params['pci_class'].str_value = '5678ABCD'
    probe_params['ata_vendor'].str_value = 'abcdefgh'
    probe_params['ata_model'].str_value = 'abcdefgh12345678'
    ret = self._probe_tool_manager.ValidateProbeInfo(
        self._GENERIC_STORAGE_FUNC_NAME, list(probe_params.values()))
    self.assertTrue(ret.is_passed)

    # Should only give probe parameters of at most one kind of HW interface.
    with self.assertRaises(ValueError):
      ret = self._probe_tool_manager.GenerateProbeStatement(
          self._GENERIC_STORAGE_FUNC_NAME, list(probe_params.values()),
          "comp_name")

  def _GenerateEmptyProbeParametersForStorage(self):
    return {name: stubby_pb2.ProbeParameter(name=name, str_value='')
            for name in ['manfid', 'oemid', 'name', 'prv', 'pci_vendor',
                         'pci_device', 'pci_class', 'ata_vendor', 'ata_model']}


if __name__ == '__main__':
  unittest.main()
