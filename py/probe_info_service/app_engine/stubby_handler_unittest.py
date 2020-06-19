# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

from cros.factory.probe_info_service.app_engine import probe_metainfo_connector
from cros.factory.probe_info_service.app_engine import ps_storage_connector
from cros.factory.probe_info_service.app_engine import stubby_handler
# pylint: disable=no-name-in-module
from cros.factory.probe_info_service.app_engine import stubby_pb2
# pylint: enable=no-name-in-module
from cros.factory.probe_info_service.app_engine import unittest_utils


class StubbyHandlerTest(unittest.TestCase):
  def setUp(self):
    probe_metainfo_connector.GetProbeMetaInfoConnectorInstance().Clean()
    ps_storage_connector.GetProbeStatementStorageConnector().Clean()

    self._stubby_handler = stubby_handler.ProbeInfoService()

  def test_GetProbeSchema(self):
    # This API is stateless, so just simply verify the call stack.
    req = stubby_pb2.GetProbeSchemaRequest()
    resp = self._stubby_handler.GetProbeSchema(req)
    self.assertCountEqual(
        [f.name for f in resp.probe_schema.probe_function_definitions],
        ['battery.generic_battery', 'storage.mmc_storage',
         'storage.nvme_storage'])

  def test_StatefulAPIs_Scenario1(self):
    # 1. The user validates the probe info and finds format error.
    req = stubby_pb2.ValidateProbeInfoRequest(
        is_qual=True, probe_info=unittest_utils.LoadComponentProbeInfo(
            '1-param_value_error').probe_info)
    resp = self._stubby_handler.ValidateProbeInfo(req)
    self.assertEqual(
        resp.probe_info_parsed_result,
        unittest_utils.LoadProbeInfoParsedResult('1-param_value_error'))

    # 2. After probe info fixup, the user creates a qual test bundle.
    req = stubby_pb2.GetQualProbeTestBundleRequest(
        qual_probe_info=unittest_utils.LoadComponentProbeInfo('1-valid'))
    resp = self._stubby_handler.GetQualProbeTestBundle(req)
    self.assertEqual(resp.result_type, resp.SUCCEED)
    qual_probe_info = req.qual_probe_info

    # 3. The user gets a differnet test bundle from a different probe info.
    req = stubby_pb2.GetQualProbeTestBundleRequest(
        qual_probe_info=unittest_utils.LoadComponentProbeInfo('1-valid_v2'))
    resp = self._stubby_handler.GetQualProbeTestBundle(req)
    self.assertEqual(resp.result_type, resp.SUCCEED)
    qual_probe_info_v2 = req.qual_probe_info

    # 4. The user uploads a positive result for the first bundle, get "LEGACY"
    #    notification.
    req = stubby_pb2.UploadQualProbeTestResultRequest(
        qual_probe_info=qual_probe_info_v2,
        test_result_payload=unittest_utils.LoadRawProbedOutcome('1-passed'))
    resp = self._stubby_handler.UploadQualProbeTestResult(req)
    self.assertTrue(resp.is_uploaded_payload_valid)
    self.assertEqual(resp.probe_info_test_result.result_type,
                     resp.probe_info_test_result.LEGACY)

    req = stubby_pb2.GetProbeMetadataRequest(
        component_probe_infos=[qual_probe_info_v2])
    resp = self._stubby_handler.GetProbeMetadata(req)
    self.assertFalse(resp.probe_metadatas[0].is_tested)

    # 5. The user then uploads the second positive test bundle and get
    #    "PASSED".  Now the qual probe info become "tested".
    req = stubby_pb2.UploadQualProbeTestResultRequest(
        qual_probe_info=qual_probe_info_v2,
        test_result_payload=unittest_utils.LoadRawProbedOutcome('1-passed_v2'))
    resp = self._stubby_handler.UploadQualProbeTestResult(req)
    self.assertTrue(resp.is_uploaded_payload_valid)
    self.assertEqual(resp.probe_info_test_result.result_type,
                     resp.probe_info_test_result.PASSED)

    req = stubby_pb2.GetProbeMetadataRequest(
        component_probe_infos=[qual_probe_info_v2])
    resp = self._stubby_handler.GetProbeMetadata(req)
    self.assertTrue(resp.probe_metadatas[0].is_tested)

    # 6. The user modifies the probe info again.  Now the qual probe info
    #    becomes "untested" again.
    req = stubby_pb2.GetProbeMetadataRequest(
        component_probe_infos=[qual_probe_info])
    resp = self._stubby_handler.GetProbeMetadata(req)
    self.assertFalse(resp.probe_metadatas[0].is_tested)

  def test_StatefulAPIs_Scenario2(self):
    ps_storage_connector_inst = (
        ps_storage_connector.GetProbeStatementStorageConnector())

    qual_probe_info = unittest_utils.LoadComponentProbeInfo('1-valid')
    qual_id = qual_probe_info.component_identity.qual_id
    get_probe_metadata_req = stubby_pb2.GetProbeMetadataRequest(
        component_probe_infos=[qual_probe_info])

    # 1. The user creates a qual test bundle, then uploading an negative probe
    #    result.
    req = stubby_pb2.GetQualProbeTestBundleRequest(
        qual_probe_info=qual_probe_info)
    self._stubby_handler.GetQualProbeTestBundle(req)

    req = stubby_pb2.UploadQualProbeTestResultRequest(
        qual_probe_info=qual_probe_info,
        test_result_payload=unittest_utils.LoadRawProbedOutcome(
            '1-bad_return_code'))
    resp = self._stubby_handler.UploadQualProbeTestResult(req)
    self.assertTrue(resp.is_uploaded_payload_valid)
    self.assertEqual(resp.probe_info_test_result.result_type,
                     resp.probe_info_test_result.INTRIVIAL_ERROR)

    # Verify the probe metadata.
    resp = self._stubby_handler.GetProbeMetadata(get_probe_metadata_req)
    self.assertFalse(resp.probe_metadatas[0].is_overridden)
    self.assertFalse(resp.probe_metadatas[0].is_tested)
    self.assertTrue(resp.probe_metadatas[0].is_proved_ready_for_overridden)

    # 2. The user creates an overridden probe statement for the qualification.
    req = stubby_pb2.CreateOverriddenProbeStatementRequest(
        component_probe_info=qual_probe_info)
    resp = self._stubby_handler.CreateOverriddenProbeStatement(req)
    self.assertEqual(resp.result_type, resp.SUCCEED)

    # Try to make the request again and the service should block it.
    resp = self._stubby_handler.CreateOverriddenProbeStatement(req)
    self.assertEqual(resp.result_type, resp.ALREADY_OVERRIDDEN_ERROR)

    # Verify the probe metadata.
    resp = self._stubby_handler.GetProbeMetadata(get_probe_metadata_req)
    self.assertTrue(resp.probe_metadatas[0].is_overridden)
    self.assertFalse(resp.probe_metadatas[0].is_tested)

    # 3. The user modifies the overridden probe statement, then downloads the
    #    qual test bundle.
    probe_data = ps_storage_connector_inst.TryLoadOverriddenQualProbeData(
        qual_id)
    probe_data.probe_statement = unittest_utils.LoadProbeStatementString(
        '1-invalid')
    ps_storage_connector_inst.UpdateOverriddenQualProbeData(qual_id, probe_data)

    req = stubby_pb2.GetQualProbeTestBundleRequest(
        qual_probe_info=qual_probe_info)
    resp = self._stubby_handler.GetQualProbeTestBundle(req)
    self.assertEqual(resp.result_type, resp.INVALID_PROBE_INFO)
    self.assertEqual(
        resp.probe_info_parsed_result.result_type,
        resp.probe_info_parsed_result.OVERRIDDEN_PROBE_STATEMENT_ERROR)

    probe_data = ps_storage_connector_inst.TryLoadOverriddenQualProbeData(
        qual_id)
    probe_data.probe_statement = unittest_utils.LoadProbeStatementString(
        '1-valid_modified')
    ps_storage_connector_inst.UpdateOverriddenQualProbeData(qual_id, probe_data)

    req = stubby_pb2.GetQualProbeTestBundleRequest(
        qual_probe_info=qual_probe_info)
    resp = self._stubby_handler.GetQualProbeTestBundle(req)
    self.assertEqual(resp.result_type, resp.SUCCEED)

    # 4. The user upload a positive probe result, the probe statement should
    #    become tested now.
    req = stubby_pb2.UploadQualProbeTestResultRequest(
        qual_probe_info=qual_probe_info,
        test_result_payload=unittest_utils.LoadRawProbedOutcome(
            '1-modified_probe_statement_passed'))
    resp = self._stubby_handler.UploadQualProbeTestResult(req)
    self.assertTrue(resp.is_uploaded_payload_valid)
    self.assertEqual(resp.probe_info_test_result.result_type,
                     resp.probe_info_test_result.PASSED)

    resp = self._stubby_handler.GetProbeMetadata(get_probe_metadata_req)
    self.assertTrue(resp.probe_metadatas[0].is_overridden)
    self.assertTrue(resp.probe_metadatas[0].is_tested)

    # 5. The user modifies the overridden probe statement, drop the tested flag.
    probe_data = ps_storage_connector_inst.TryLoadOverriddenQualProbeData(
        qual_id)
    probe_data.is_tested = False
    ps_storage_connector_inst.UpdateOverriddenQualProbeData(qual_id, probe_data)

    resp = self._stubby_handler.GetProbeMetadata(get_probe_metadata_req)
    self.assertTrue(resp.probe_metadatas[0].is_overridden)
    self.assertFalse(resp.probe_metadatas[0].is_tested)


if __name__ == '__main__':
  unittest.main()
