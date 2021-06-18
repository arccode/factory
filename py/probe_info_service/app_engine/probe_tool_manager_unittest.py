# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import os.path
import unittest
import tempfile

from google.protobuf import text_format

# pylint: disable=no-name-in-module
from cros.factory.probe_info_service.app_engine import client_payload_pb2
# pylint: enable=no-name-in-module
from cros.factory.probe_info_service.app_engine import probe_tool_manager
from cros.factory.probe_info_service.app_engine import stubby_handler
# pylint: disable=no-name-in-module
from cros.factory.probe_info_service.app_engine import stubby_pb2
# pylint: enable=no-name-in-module
from cros.factory.probe_info_service.app_engine import unittest_utils
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils
from cros.factory.utils import process_utils


def _LoadProbeInfoAndCompName(testdata_name):
  comp_probe_info = unittest_utils.LoadComponentProbeInfo(testdata_name)
  comp_name = stubby_handler.GetProbeDataSourceComponentName(
      comp_probe_info.component_identity)
  return comp_probe_info.probe_info, comp_name


class ProbeToolManagerTest(unittest.TestCase):
  def setUp(self):
    self._probe_tool_manager = probe_tool_manager.ProbeToolManager()

  def test_GetProbeSchema(self):
    resp = self._probe_tool_manager.GetProbeSchema()
    self.assertCountEqual([f.name for f in resp.probe_function_definitions],
                          ['battery.generic_battery', 'storage.mmc_storage',
                           'storage.nvme_storage'])

  def test_ValidateProbeInfo_InvalidProbeFunction(self):
    probe_info = probe_tool_manager.ProbeInfo(probe_function_name='no_such_f')
    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, True)
    self.assertEqual(resp.result_type, resp.INCOMPATIBLE_ERROR)

  def test_ValidateProbeInfo_UnknownProbeParameter(self):
    probe_info, unused_comp_name = _LoadProbeInfoAndCompName('1-valid')
    probe_info.probe_parameters.add(name='no_such_param')

    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, True)
    self.assertEqual(resp.result_type, resp.INCOMPATIBLE_ERROR)

  def test_ValidateProbeInfo_ProbeParameterBadType(self):
    probe_info, unused_comp_name = _LoadProbeInfoAndCompName('1-valid')
    for probe_param in probe_info.probe_parameters:
      if probe_param.name == 'mmc_manfid':
        probe_param.string_value = ''
        probe_param.int_value = 123

    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, True)
    self.assertEqual(resp.result_type, resp.INCOMPATIBLE_ERROR)

  def test_ValidateProbeInfo_DuplicatedParam(self):
    # Duplicated probe parameters is a kind of compatible error for now.
    probe_info, unused_comp_name = _LoadProbeInfoAndCompName('1-valid')
    probe_info.probe_parameters.add(name='mmc_manfid', string_value='03')

    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, True)
    self.assertEqual(resp.result_type, resp.INCOMPATIBLE_ERROR)

  def test_ValidateProbeInfo_MissingProbeParameter(self):
    # Missing probe parameters is a kind of compatible error unless
    # `allow_missing_parameters` is `True`.
    probe_info, unused_comp_name = _LoadProbeInfoAndCompName('1-valid')
    for probe_param in probe_info.probe_parameters:
      if probe_param.name == 'mmc_manfid':
        probe_info.probe_parameters.remove(probe_param)
        break

    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, False)
    self.assertEqual(resp.result_type, resp.INCOMPATIBLE_ERROR)

    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, True)
    self.assertEqual(resp.result_type, resp.PASSED)

  def test_ValidateProbeInfo_ParameterFormatError(self):
    probe_info, unused_comp_name = _LoadProbeInfoAndCompName(
        '1-param_value_error')
    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, False)
    self.assertEqual(resp, unittest_utils.LoadProbeInfoParsedResult(
        '1-param_value_error'))

  def test_ValidateProbeInfo_Passed(self):
    probe_info, unused_comp_name = _LoadProbeInfoAndCompName('1-valid')
    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, False)
    self.assertEqual(resp.result_type, resp.PASSED)

    probe_info, unused_comp_name = _LoadProbeInfoAndCompName('2-valid')
    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, False)
    self.assertEqual(resp.result_type, resp.PASSED)

    probe_info, unused_comp_name = _LoadProbeInfoAndCompName('3-valid')
    resp = self._probe_tool_manager.ValidateProbeInfo(probe_info, False)
    self.assertEqual(resp.result_type, resp.PASSED)

  def test_CreateProbeDataSource(self):
    s1 = self._LoadProbeDataSource('1-valid', comp_name='aaa')
    s2 = self._LoadProbeDataSource('2-valid', comp_name='aaa')
    s3 = self._LoadProbeDataSource('1-valid', comp_name='bbb')
    self.assertNotEqual(s1.fingerprint, s2.fingerprint)
    self.assertEqual(s1.fingerprint, s3.fingerprint)

  def test_DumpProbeDataSource(self):
    s = self._LoadProbeDataSource('1-valid')
    ps = self._probe_tool_manager.DumpProbeDataSource(s).output
    self._AssertJSONStringEqual(
        ps, unittest_utils.LoadProbeStatementString('1-default'))

  def test_GenerateRawProbeStatement_FromValidProbeInfo(self):
    s = self._LoadProbeDataSource('1-valid')
    ps = self._probe_tool_manager.GenerateRawProbeStatement(s).output
    self._AssertJSONStringEqual(
        ps, unittest_utils.LoadProbeStatementString('1-default'))

  def test_GenerateRawProbeStatement_FromInvalidProbeInfo(self):
    s = self._LoadProbeDataSource('1-param_value_error')
    gen_result = self._probe_tool_manager.GenerateRawProbeStatement(s)
    self.assertEqual(
        gen_result.probe_info_parsed_result,
        unittest_utils.LoadProbeInfoParsedResult('1-param_value_error'))
    self.assertIsNone(gen_result.output)

  def test_GenerateRawProbeStatement_FromOverriddenProbeStatement(self):
    overridden_ps = unittest_utils.LoadProbeStatementString('1-valid_modified')
    s = self._probe_tool_manager.LoadProbeDataSource('comp_name', overridden_ps)
    generated_ps = self._probe_tool_manager.GenerateRawProbeStatement(s).output
    self._AssertJSONStringEqual(generated_ps, overridden_ps)

  def test_GenerateProbeBundlePayload_ProbeParameterError(self):
    s = self._LoadProbeDataSource('1-param_value_error')
    resp = self._probe_tool_manager.GenerateProbeBundlePayload([s])
    self.assertEqual(
        resp.probe_info_parsed_results[0],
        unittest_utils.LoadProbeInfoParsedResult('1-param_value_error'))

  def test_GenerateProbeBundlePayload_IncompatibleError(self):
    probe_info, comp_name = _LoadProbeInfoAndCompName('1-valid')
    for probe_param in probe_info.probe_parameters:
      if probe_param.name == 'mmc_manfid':
        probe_info.probe_parameters.remove(probe_param)
        break
    resp = self._probe_tool_manager.GenerateProbeBundlePayload([
        self._probe_tool_manager.CreateProbeDataSource(comp_name, probe_info)])
    self.assertEqual(resp.probe_info_parsed_results[0].result_type,
                     resp.probe_info_parsed_results[0].INCOMPATIBLE_ERROR)

  def test_GenerateQualProbeTestBundlePayload_Passed(self):
    info = unittest_utils.FakeProbedOutcomeInfo('1-succeed')

    resp = self._GenerateProbeBundlePayloadForFakeRuntimeProbe(info)
    self.assertEqual(resp.probe_info_parsed_results[0].result_type,
                     resp.probe_info_parsed_results[0].PASSED)

    # Invoke the probe bundle file with a fake `runtime_probe` to verify if the
    # probe bundle works.
    unpacked_dir, probed_outcome = self._InvokeProbeBundleWithFakeRuntimeProbe(
        resp.output.content, info.envs)
    arg_str, pc_payload = self._ExtractFakeRuntimeProbeStderr(probed_outcome)
    self.assertEqual(probed_outcome, info.probed_outcome)
    self.assertEqual(arg_str,
                     self._GetExpectedRuntimeProbeArguments(unpacked_dir))
    self._AssertJSONStringEqual(pc_payload, info.probe_config_payload)

  def test_GenerateQualProbeTestBundlePayload_MultipleSourcePassed(self):
    info = unittest_utils.FakeProbedOutcomeInfo('1_2-succeed')

    resp = self._GenerateProbeBundlePayloadForFakeRuntimeProbe(info)
    self.assertEqual(resp.probe_info_parsed_results[0].result_type,
                     resp.probe_info_parsed_results[0].PASSED)
    self.assertEqual(resp.probe_info_parsed_results[1].result_type,
                     resp.probe_info_parsed_results[1].PASSED)

    # Invoke the probe bundle file with a fake `runtime_probe` to verify if the
    # probe bundle works.
    unpacked_dir, probed_outcome = self._InvokeProbeBundleWithFakeRuntimeProbe(
        resp.output.content, info.envs)
    arg_str, pc_payload = self._ExtractFakeRuntimeProbeStderr(probed_outcome)
    self.assertEqual(probed_outcome, info.probed_outcome)
    self.assertEqual(arg_str,
                     self._GetExpectedRuntimeProbeArguments(unpacked_dir))
    self._AssertJSONStringEqual(pc_payload, info.probe_config_payload)

  def test_GenerateQualProbeTestBundlePayload_NoRuntimeProbe(self):
    info = unittest_utils.FakeProbedOutcomeInfo('1-bin_not_found')

    resp = self._GenerateProbeBundlePayloadForFakeRuntimeProbe(info)
    self.assertEqual(resp.probe_info_parsed_results[0].result_type,
                     resp.probe_info_parsed_results[0].PASSED)

    unused_unpacked_dir, probed_outcome = (
        self._InvokeProbeBundleWithFakeRuntimeProbe(resp.output.content,
                                                    info.envs))
    self.assertTrue(bool(probed_outcome.rp_invocation_result.error_msg))
    self.assertEqual(probed_outcome, info.probed_outcome)

  def test_AnalyzeQualProbeTestResult_PayloadFormatError(self):
    s = self._LoadProbeDataSource('1-valid')
    with self.assertRaises(probe_tool_manager.PayloadInvalidError):
      self._probe_tool_manager.AnalyzeQualProbeTestResultPayload(
          s, 'this_is_an_invalid_data')

  def test_AnalyzeQualProbeTestResult_WrongComponentError(self):
    s = self._LoadProbeDataSource('1-valid')
    raw_probed_outcome = unittest_utils.LoadRawProbedOutcome(
        '1-wrong_component')
    with self.assertRaises(probe_tool_manager.PayloadInvalidError):
      self._probe_tool_manager.AnalyzeQualProbeTestResultPayload(
          s, raw_probed_outcome)

  def test_AnalyzeQualProbeTestResult_Pass(self):
    s = self._LoadProbeDataSource('1-valid')
    raw_probed_outcome = unittest_utils.LoadRawProbedOutcome('1-passed')
    resp = self._probe_tool_manager.AnalyzeQualProbeTestResultPayload(
        s, raw_probed_outcome)
    self.assertEqual(resp.result_type, resp.PASSED)

  def test_AnalyzeQualProbeTestResult_Legacy(self):
    s = self._LoadProbeDataSource('1-valid')
    raw_probed_outcome = unittest_utils.LoadRawProbedOutcome('1-legacy')
    resp = self._probe_tool_manager.AnalyzeQualProbeTestResultPayload(
        s, raw_probed_outcome)
    self.assertEqual(resp.result_type, resp.LEGACY)

  def test_AnalyzeQualProbeTestResult_IntrivialError_BadReturnCode(self):
    s = self._LoadProbeDataSource('1-valid')
    raw_probed_outcome = unittest_utils.LoadRawProbedOutcome(
        '1-bad_return_code')
    resp = self._probe_tool_manager.AnalyzeQualProbeTestResultPayload(
        s, raw_probed_outcome)
    self.assertEqual(resp.result_type, resp.INTRIVIAL_ERROR)

  def test_AnalyzeQualProbeTestResult_IntrivialError_InvalidProbeResult(self):
    s = self._LoadProbeDataSource('1-valid')
    raw_probed_outcome = unittest_utils.LoadRawProbedOutcome(
        '1-invalid_probe_result')
    resp = self._probe_tool_manager.AnalyzeQualProbeTestResultPayload(
        s, raw_probed_outcome)
    self.assertEqual(resp.result_type, resp.INTRIVIAL_ERROR)

  def test_AnalyzeQualProbeTestResult_IntrivialError_ProbeResultMismatch(self):
    s = self._LoadProbeDataSource('1-valid')
    raw_probed_outcome = unittest_utils.LoadRawProbedOutcome(
        '1-probe_result_not_match_metadata')
    resp = self._probe_tool_manager.AnalyzeQualProbeTestResultPayload(
        s, raw_probed_outcome)
    self.assertEqual(resp.result_type, resp.INTRIVIAL_ERROR)

  def test_AnalyzeQualProbeTestResult_IntrivialError_RuntimeProbeTimeout(self):
    s = self._LoadProbeDataSource('1-valid')
    raw_probed_outcome = unittest_utils.LoadRawProbedOutcome('1-timeout')
    resp = self._probe_tool_manager.AnalyzeQualProbeTestResultPayload(
        s, raw_probed_outcome)
    self.assertEqual(resp.result_type, resp.INTRIVIAL_ERROR)

  def test_AnalyzeDeviceProbeResultPayload_FormatError(self):
    s1 = self._LoadProbeDataSource('1-valid')
    s2 = self._LoadProbeDataSource('2-valid')
    raw_probed_outcome = 'this is not a valid probed outcome'
    with self.assertRaises(probe_tool_manager.PayloadInvalidError):
      self._probe_tool_manager.AnalyzeDeviceProbeResultPayload(
          [s1, s2], raw_probed_outcome)

  def test_AnalyzeDeviceProbeResultPayload_HasUnknownComponentError(self):
    s1 = self._LoadProbeDataSource('1-valid')
    s2 = self._LoadProbeDataSource('2-valid')
    with self.assertRaises(probe_tool_manager.PayloadInvalidError):
      self._probe_tool_manager.AnalyzeDeviceProbeResultPayload(
          [s1, s2],
          unittest_utils.LoadRawProbedOutcome('1_2-has_unknown_component'))

  def test_AnalyzeDeviceProbeResultPayload_IntrivialError(self):
    s1 = self._LoadProbeDataSource('1-valid')
    s2 = self._LoadProbeDataSource('2-valid')
    result = self._probe_tool_manager.AnalyzeDeviceProbeResultPayload(
        [s1, s2],
        unittest_utils.LoadRawProbedOutcome('1_2-runtime_probe_crash'))
    self.assertIsNotNone(result.intrivial_error_msg)
    self.assertIsNone(result.probe_info_test_results)

  def test_AnalyzeDeviceProbeResultPayload_Passed(self):
    s1 = self._LoadProbeDataSource('1-valid')
    s2 = self._LoadProbeDataSource('2-valid')
    s3 = self._LoadProbeDataSource('3-valid')
    s4 = self._LoadProbeDataSource('1-valid', comp_name='yet_another_component')
    result = self._probe_tool_manager.AnalyzeDeviceProbeResultPayload(
        [s1, s2, s3, s4], unittest_utils.LoadRawProbedOutcome('1_2_3-valid'))
    self.assertIsNone(result.intrivial_error_msg)
    self.assertEqual([r.result_type for r in result.probe_info_test_results],
                     [stubby_pb2.ProbeInfoTestResult.NOT_PROBED,
                      stubby_pb2.ProbeInfoTestResult.PASSED,
                      stubby_pb2.ProbeInfoTestResult.LEGACY,
                      stubby_pb2.ProbeInfoTestResult.NOT_INCLUDED])

  def _AssertJSONStringEqual(self, lhs, rhs):
    self.assertEqual(json_utils.LoadStr(lhs), json_utils.LoadStr(rhs))

  def _LoadProbeDataSource(self, testdata_name, comp_name=None):
    probe_info, default_comp_name = _LoadProbeInfoAndCompName(testdata_name)
    return self._probe_tool_manager.CreateProbeDataSource(
        comp_name or default_comp_name, probe_info)

  def _GenerateProbeBundlePayloadForFakeRuntimeProbe(self,
                                                     fake_probe_outcome_info):
    probe_info_sources = []
    for testdata_name in fake_probe_outcome_info.component_testdata_names:
      probe_info_sources.append(self._LoadProbeDataSource(testdata_name))
    return self._probe_tool_manager.GenerateProbeBundlePayload(
        probe_info_sources)

  def _InvokeProbeBundleWithFakeRuntimeProbe(self, probe_bundle_payload, envs):
    probe_bundle_path = file_utils.CreateTemporaryFile()
    os.chmod(probe_bundle_path, 0o755)
    file_utils.WriteFile(probe_bundle_path, probe_bundle_payload, encoding=None)

    unpacked_dir = tempfile.mkdtemp()
    with file_utils.TempDirectory() as fake_bin_path:
      file_utils.ForceSymlink(unittest_utils.FAKE_RUNTIME_PROBE_PATH,
                              os.path.join(fake_bin_path, 'runtime_probe'))
      subproc_envs = dict(os.environ)
      subproc_envs['PATH'] = fake_bin_path + ':' + subproc_envs['PATH']
      subproc_envs.update(envs)
      raw_output = process_utils.CheckOutput(
          [probe_bundle_path, '-d', unpacked_dir], env=subproc_envs,
          encoding=None)
    return unpacked_dir, text_format.Parse(
        raw_output, client_payload_pb2.ProbedOutcome())

  def _ExtractFakeRuntimeProbeStderr(self, probed_outcome):
    raw_stderr = probed_outcome.rp_invocation_result.raw_stderr.decode('utf-8')
    probed_outcome.rp_invocation_result.raw_stderr = b''
    return [s.strip(' \n') for s in raw_stderr.split('=====')]

  def _GetExpectedRuntimeProbeArguments(self, unpacked_dir):
    return ' '.join(['--config_file_path=%s/probe_config.json' % unpacked_dir,
                     '--to_stdout', '--verbosity_level=3'])


if __name__ == '__main__':
  unittest.main()
