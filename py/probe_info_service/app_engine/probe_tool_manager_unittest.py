# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

from cros.factory.probe_info_service.app_engine import probe_tool_manager
from cros.factory.utils import json_utils


class ProbeToolManagerTest(unittest.TestCase):
  def setUp(self):
    self._probe_tool_manager = probe_tool_manager.ProbeToolManager()

  def testGetProbeSchema(self):
    resp = self._probe_tool_manager.GetProbeSchema()
    self.assertCountEqual([f.name for f in resp.probe_function_definitions],
                          ['battery.generic_battery', 'storage.mmc_storage',
                           'storage.nvme_storage'])

  def testValidateProbeInfoInvalidProbeFunction(self):
    probe_info = probe_tool_manager.ProbeInfo(probe_function_name='no_such_f')
    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, True)
    self.assertEqual(resp.result_type, resp.INCOMPATIBLE_ERROR)

  def testValidateProbeInfoUnknownProbeParameter(self):
    probe_info = self._GenerateSampleMMCStorageProbeInfo(
        probe_params_construct_kwargs={'no_such_param': {}})

    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, True)
    self.assertEqual(resp.result_type, resp.INCOMPATIBLE_ERROR)

  def testValidateProbeInfoProbeParameterBadType(self):
    probe_info = self._GenerateSampleMMCStorageProbeInfo(
        probe_params_construct_kwargs={'manfid': {'int_value': 123}})

    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, True)
    self.assertEqual(resp.result_type, resp.INCOMPATIBLE_ERROR)

  def testValidateProbeInfoDuplicatedParam(self):
    # Duplicated probe parameters is a kind of compatible error for now.
    probe_info = self._GenerateSampleMMCStorageProbeInfo()
    probe_info.probe_parameters.add(name='manfid', string_value='03')

    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, True)
    self.assertEqual(resp.result_type, resp.INCOMPATIBLE_ERROR)

  def testValidateProbeInfoMissingProbeParameter(self):
    # Missing probe parameters is a kind of compatible error unless
    # `allow_missing_parameters` is `True`.
    probe_info = self._GenerateSampleMMCStorageProbeInfo(
        probe_params_construct_kwargs={'manfid': None})

    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, False)
    self.assertEqual(resp.result_type, resp.INCOMPATIBLE_ERROR)

    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, True)
    self.assertEqual(resp.result_type, resp.PASSED)

  def testValidateProbeInfoProbeParameterFormatError(self):
    probe_info = self._GenerateSampleMMCStorageProbeInfo(
        probe_params_construct_kwargs={
            # `manfid` should be a 2-digit hex string
            'manfid': {'string_value': '0?'},
            # `name` should be a 6-byte ASCII string
            'name': {'string_value': 'ABC123456789'},
        })
    expected_probe_error_index = []
    for index, param in enumerate(probe_info.probe_parameters):
      if param.name in ('name', 'manfid'):
        expected_probe_error_index.append(index)

    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, False)
    self.assertEqual(resp.result_type, resp.PROBE_PARAMETER_ERROR)
    self.assertCountEqual([p.index for p in resp.probe_parameter_errors],
                          expected_probe_error_index)

  def testValidateProbeInfoPass(self):
    probe_info = self._GenerateSampleMMCStorageProbeInfo()
    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, False)
    self.assertEqual(resp.result_type, resp.PASSED)

  def testCreateProbeDataSourceFromProbeInfo(self):
    probe_info1 = self._GenerateSampleMMCStorageProbeInfo()
    probe_info2 = self._GenerateSampleMMCStorageProbeInfo(
        probe_params_construct_kwargs={'manfid': None})
    s1 = self._probe_tool_manager.CreateProbeDataSourceFromProbeInfo(
        'aaa', probe_info1)
    s2 = self._probe_tool_manager.CreateProbeDataSourceFromProbeInfo(
        'aaa', probe_info2)
    s3 = self._probe_tool_manager.CreateProbeDataSourceFromProbeInfo(
        'bbb', probe_info1)
    self.assertNotEqual(s1.probe_info_fp, s2.probe_info_fp)
    self.assertEqual(s1.probe_info_fp, s3.probe_info_fp)

  def testGenerateQualProbeTestBundlePayloadFail(self):
    probe_info = self._GenerateSampleMMCStorageProbeInfo(
        probe_params_construct_kwargs={'manfid': {'string_value': 'bad_value'}})
    resp = self._probe_tool_manager.GenerateQualProbeTestBundlePayload(
        self._probe_tool_manager.CreateProbeDataSourceFromProbeInfo(
            'comp_name', probe_info))
    self.assertEqual(resp.probe_info_parsed_result.result_type,
                     resp.probe_info_parsed_result.PROBE_PARAMETER_ERROR)

    probe_info = self._GenerateSampleMMCStorageProbeInfo(
        probe_params_construct_kwargs={'manfid': None})
    resp = self._probe_tool_manager.GenerateQualProbeTestBundlePayload(
        self._probe_tool_manager.CreateProbeDataSourceFromProbeInfo(
            'comp_name', probe_info))
    self.assertEqual(resp.probe_info_parsed_result.result_type,
                     resp.probe_info_parsed_result.INCOMPATIBLE_ERROR)

  def testGenerateQualProbeTestBundlePayloadSuccess(self):
    probe_info = self._GenerateSampleMMCStorageProbeInfo()
    s = self._probe_tool_manager.CreateProbeDataSourceFromProbeInfo(
        'comp_name', probe_info)
    resp = self._probe_tool_manager.GenerateQualProbeTestBundlePayload(s)
    self.maxDiff = None
    self.assertEqual(
        json_utils.LoadStr(resp.payload.decode('utf-8')),
        {
            'storage': {
                'comp_name': {
                    'eval': {'mmc_storage': {}},
                    'expect': {
                        'manfid': [True, 'hex', '!eq 0x0A'],
                        'name': [True, 'str', '!eq ABCxyz'],
                        'oemid': [True, 'hex', '!eq 0x1234'],
                        'prv': [True, 'hex', '!eq 0x01'],
                        'sectors': [True, 'int', '!eq 123'],
                    },
                    'information': {
                        'PROBE_INFO_FINGERPRINT':
                            '97b346e92ad636dad26f9a1dee5e94f88c01917f',
                    },
                },
            },
        })

  def testAnalyzeQualProbeTestResultInvalidPayload(self):
    probe_info = self._GenerateSampleMMCStorageProbeInfo()
    s = self._probe_tool_manager.CreateProbeDataSourceFromProbeInfo(
        'comp_name', probe_info)
    with self.assertRaises(probe_tool_manager.PayloadInvalidError):
      self._probe_tool_manager.AnalyzeQualProbeTestResultPayload(
          s, 'this_is_an_invalid_data')

  def testAnalyzeQualProbeTestResultPass(self):
    probe_info = self._GenerateSampleMMCStorageProbeInfo()
    s = self._probe_tool_manager.CreateProbeDataSourceFromProbeInfo(
        'comp_name', probe_info)
    resp = self._probe_tool_manager.AnalyzeQualProbeTestResultPayload(
        s, json_utils.DumpStr({
            'storage': {
                'comp_name': [
                    {
                        'information': {
                            'PROBE_INFO_FINGERPRINT': s.probe_info_fp,
                        },
                    },
                ],
            },
        }).encode('utf-8'))
    self.assertEqual(resp.result_type, resp.PASSED)

  def testAnalyzeQualProbeTestResultLegacy(self):
    probe_info = self._GenerateSampleMMCStorageProbeInfo()
    s = self._probe_tool_manager.CreateProbeDataSourceFromProbeInfo(
        'comp_name', probe_info)
    resp = self._probe_tool_manager.AnalyzeQualProbeTestResultPayload(
        s, json_utils.DumpStr({
            'storage': {
                'comp_name': [
                    {
                        'information': {
                            'PROBE_INFO_FINGERPRINT': 'not_the_correct_fp',
                        },
                    },
                ],
            },
        }).encode('utf-8'))
    self.assertEqual(resp.result_type, resp.LEGACY)

  def testAnalyzeQualProbeTestResultIntirivalError(self):
    probe_info = self._GenerateSampleMMCStorageProbeInfo()
    s = self._probe_tool_manager.CreateProbeDataSourceFromProbeInfo(
        'comp_name', probe_info)
    resp = self._probe_tool_manager.AnalyzeQualProbeTestResultPayload(
        s, json_utils.DumpStr({}).encode('utf-8'))
    self.assertEqual(resp.result_type, resp.INTRIVIAL_ERROR)
    self.assertTrue(bool(resp.intrivial_error_msg))

  @staticmethod
  def _GenerateSampleMMCStorageProbeInfo(probe_params_construct_kwargs=None):
    resolved_probe_params_construct_kwargs = {
        'manfid': {'string_value': '0A'},
        'oemid': {'string_value': '1234'},
        'name': {'string_value': 'ABCxyz'},
        'prv': {'string_value': '01'},
        'sectors': {'int_value': 123},
    }
    resolved_probe_params_construct_kwargs.update(
        probe_params_construct_kwargs or {})

    probe_info = probe_tool_manager.ProbeInfo(
        probe_function_name='storage.mmc_storage')
    for param_name, kwargs in resolved_probe_params_construct_kwargs.items():
      if kwargs is None:
        continue
      probe_info.probe_parameters.add(name=param_name, **kwargs)

    return probe_info


if __name__ == '__main__':
  unittest.main()
