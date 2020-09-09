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

  def test_GetProbeMetadata_IncludeProbeStatementPreviewOfValidInput(self):
    req = stubby_pb2.GetProbeMetadataRequest(
        component_probe_infos=[
            unittest_utils.LoadComponentProbeInfo('1-valid')
        ], include_probe_statement_preview=True)
    resp = self._stubby_handler.GetProbeMetadata(req)
    self.assertEqual(resp.probe_metadatas[0].probe_statement_preview,
                     unittest_utils.LoadProbeStatementString('1-default'))

  def test_GetProbeMetadata_IncludeProbeStatementPreviewOfInvalidInput(self):
    req = stubby_pb2.GetProbeMetadataRequest(
        component_probe_infos=[
            unittest_utils.LoadComponentProbeInfo('1-param_value_error')
        ], include_probe_statement_preview=True)
    resp = self._stubby_handler.GetProbeMetadata(req)
    self.assertEqual(
        resp.probe_metadatas[0].probe_statement_preview,
        self._stubby_handler.MSG_NO_PROBE_STATEMENT_PREVIEW_INVALID_AVL_DATA)

  def test_GetProbeMetadata_IncludeProbeStatementPreviewWithOverridden(self):
    # Setup a qualification with overridden probe statement for the test.
    qual_probe_info = unittest_utils.LoadComponentProbeInfo('1-valid')
    qual_id = qual_probe_info.component_identity.qual_id
    self._stubby_handler.CreateOverriddenProbeStatement(
        stubby_pb2.CreateOverriddenProbeStatementRequest(
            component_probe_info=qual_probe_info))
    ps_storage_connector_inst = (
        ps_storage_connector.GetProbeStatementStorageConnector())
    probe_data = ps_storage_connector_inst.TryLoadOverriddenProbeData(
        qual_id, '')
    overridden_ps = unittest_utils.LoadProbeStatementString('1-invalid')
    probe_data.probe_statement = overridden_ps
    ps_storage_connector_inst.UpdateOverriddenProbeData(qual_id, '', probe_data)

    # Verify if the returned preview string is the overridden one.
    req = stubby_pb2.GetProbeMetadataRequest(
        component_probe_infos=[
            unittest_utils.LoadComponentProbeInfo('1-param_value_error')
        ], include_probe_statement_preview=True)
    resp = self._stubby_handler.GetProbeMetadata(req)
    self.assertEqual(resp.probe_metadatas[0].probe_statement_preview,
                     overridden_ps)

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
    self.assertEqual(resp.status, resp.SUCCEED)
    qual_probe_info = req.qual_probe_info

    # 3. The user gets a differnet test bundle from a different probe info.
    req = stubby_pb2.GetQualProbeTestBundleRequest(
        qual_probe_info=unittest_utils.LoadComponentProbeInfo('1-valid_v2'))
    resp = self._stubby_handler.GetQualProbeTestBundle(req)
    self.assertEqual(resp.status, resp.SUCCEED)
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
    self.assertEqual(resp.probe_metadatas[0].probe_statement_type,
                     resp.probe_metadatas[0].AUTO_GENERATED)
    self.assertFalse(resp.probe_metadatas[0].is_tested)
    self.assertTrue(resp.probe_metadatas[0].is_proved_ready_for_overridden)

    # 2. The user creates an overridden probe statement for the qualification.
    req = stubby_pb2.CreateOverriddenProbeStatementRequest(
        component_probe_info=qual_probe_info)
    resp = self._stubby_handler.CreateOverriddenProbeStatement(req)
    self.assertEqual(resp.status, resp.SUCCEED)

    # Try to make the request again and the service should block it.
    resp = self._stubby_handler.CreateOverriddenProbeStatement(req)
    self.assertEqual(resp.status, resp.ALREADY_OVERRIDDEN_ERROR)

    # Verify the probe metadata.
    resp = self._stubby_handler.GetProbeMetadata(get_probe_metadata_req)
    self.assertEqual(resp.probe_metadatas[0].probe_statement_type,
                     resp.probe_metadatas[0].QUAL_OVERRIDDEN)
    self.assertFalse(resp.probe_metadatas[0].is_tested)

    # 3. The user modifies the overridden probe statement, then downloads the
    #    qual test bundle.
    probe_data = ps_storage_connector_inst.TryLoadOverriddenProbeData(
        qual_id, '')
    probe_data.probe_statement = unittest_utils.LoadProbeStatementString(
        '1-invalid')
    ps_storage_connector_inst.UpdateOverriddenProbeData(qual_id, '', probe_data)

    req = stubby_pb2.GetQualProbeTestBundleRequest(
        qual_probe_info=qual_probe_info)
    resp = self._stubby_handler.GetQualProbeTestBundle(req)
    self.assertEqual(resp.status, resp.INVALID_PROBE_INFO)
    self.assertEqual(
        resp.probe_info_parsed_result.result_type,
        resp.probe_info_parsed_result.OVERRIDDEN_PROBE_STATEMENT_ERROR)

    probe_data = ps_storage_connector_inst.TryLoadOverriddenProbeData(
        qual_id, '')
    probe_data.probe_statement = unittest_utils.LoadProbeStatementString(
        '1-valid_modified')
    ps_storage_connector_inst.UpdateOverriddenProbeData(qual_id, '', probe_data)

    req = stubby_pb2.GetQualProbeTestBundleRequest(
        qual_probe_info=qual_probe_info)
    resp = self._stubby_handler.GetQualProbeTestBundle(req)
    self.assertEqual(resp.status, resp.SUCCEED)

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
    self.assertEqual(resp.probe_metadatas[0].probe_statement_type,
                     resp.probe_metadatas[0].QUAL_OVERRIDDEN)
    self.assertTrue(resp.probe_metadatas[0].is_tested)

    # 5. The user modifies the overridden probe statement, drop the tested flag.
    probe_data = ps_storage_connector_inst.TryLoadOverriddenProbeData(
        qual_id, '')
    probe_data.is_tested = False
    ps_storage_connector_inst.UpdateOverriddenProbeData(qual_id, '', probe_data)

    resp = self._stubby_handler.GetProbeMetadata(get_probe_metadata_req)
    self.assertEqual(resp.probe_metadatas[0].probe_statement_type,
                     resp.probe_metadatas[0].QUAL_OVERRIDDEN)
    self.assertFalse(resp.probe_metadatas[0].is_tested)

  def test_StatefulAPIs_Scenario3(self):
    # 3 qualifications (Q1, Q2 and Q3) and two devices (D1, D2) are involved.

    ps_storage_connector_inst = (
        ps_storage_connector.GetProbeStatementStorageConnector())

    # 1. Creates and modifies overridden probe statement for Q1.
    qual_probe_info_1 = unittest_utils.LoadComponentProbeInfo('1-valid')
    req = stubby_pb2.CreateOverriddenProbeStatementRequest(
        component_probe_info=qual_probe_info_1)
    resp = self._stubby_handler.CreateOverriddenProbeStatement(req)
    self.assertEqual(resp.status, resp.SUCCEED)

    probe_data = ps_storage_connector_inst.TryLoadOverriddenProbeData(
        qual_probe_info_1.component_identity.qual_id, '')
    probe_data.probe_statement = unittest_utils.LoadProbeStatementString(
        '1-valid_modified')
    ps_storage_connector_inst.UpdateOverriddenProbeData(
        qual_probe_info_1.component_identity.qual_id, '', probe_data)

    # 2. Creates D1 overridden qualification for Q3.
    req = stubby_pb2.CreateOverriddenProbeStatementRequest(
        component_probe_info=unittest_utils.LoadComponentProbeInfo('3-valid'))
    req.component_probe_info.component_identity.device_id = 'device_one'
    resp = self._stubby_handler.CreateOverriddenProbeStatement(req)
    self.assertEqual(resp.status, resp.SUCCEED)

    # 3. Downloads D1 probe bundle for Q1, Q2, Q3.
    comp_probe_infos = [unittest_utils.LoadComponentProbeInfo('1-valid'),
                        unittest_utils.LoadComponentProbeInfo('2-valid'),
                        unittest_utils.LoadComponentProbeInfo('3-valid')]
    for comp_probe_info in comp_probe_infos:
      comp_probe_info.component_identity.device_id = 'device_one'
    req = stubby_pb2.GetDeviceProbeConfigRequest(
        component_probe_infos=comp_probe_infos)
    resp = self._stubby_handler.GetDeviceProbeConfig(req)
    self.assertEqual(resp.status, resp.SUCCEED)

    # 4. Uploads D1 probe result, which found Q2 and Q3.
    req = stubby_pb2.UploadDeviceProbeResultRequest(
        component_probe_infos=comp_probe_infos,
        probe_result_payload=unittest_utils.LoadRawProbedOutcome(
            '1_2_3-probed_2_3'))
    resp = self._stubby_handler.UploadDeviceProbeResult(req)
    self.assertEqual(resp.upload_status, resp.SUCCEED)
    self.assertEqual([r.result_type for r in resp.probe_info_test_results],
                     [stubby_pb2.ProbeInfoTestResult.NOT_PROBED,
                      stubby_pb2.ProbeInfoTestResult.PASSED,
                      stubby_pb2.ProbeInfoTestResult.PASSED])

    # 5. Queries the probe status of Q1, Q2 and Q3 for D2.  The expected
    #    response shows that Q1 overridden but not tested, Q2 tested and Q3 not
    #    tested.
    for comp_probe_info in comp_probe_infos:
      comp_probe_info.component_identity.device_id = 'device_two'
    req = stubby_pb2.GetProbeMetadataRequest(
        component_probe_infos=comp_probe_infos)
    resp = self._stubby_handler.GetProbeMetadata(req)
    self.assertEqual(
        [(m.probe_statement_type, m.is_tested) for m in resp.probe_metadatas],
        [
            (stubby_pb2.ProbeMetadata.QUAL_OVERRIDDEN, False),
            (stubby_pb2.ProbeMetadata.AUTO_GENERATED, True),
            (stubby_pb2.ProbeMetadata.AUTO_GENERATED, False),
        ])

    # 6. Uploads positive test results for Q1 and Q3.
    req = stubby_pb2.UploadQualProbeTestResultRequest(
        qual_probe_info=unittest_utils.LoadComponentProbeInfo('1-valid'),
        test_result_payload=unittest_utils.LoadRawProbedOutcome(
            '1-modified_probe_statement_passed'))
    resp = self._stubby_handler.UploadQualProbeTestResult(req)
    self.assertEqual(resp.probe_info_test_result.result_type,
                     resp.probe_info_test_result.PASSED)

    req = stubby_pb2.UploadQualProbeTestResultRequest(
        qual_probe_info=unittest_utils.LoadComponentProbeInfo('3-valid'),
        test_result_payload=unittest_utils.LoadRawProbedOutcome('3-passed'))
    resp = self._stubby_handler.UploadQualProbeTestResult(req)
    self.assertEqual(resp.probe_info_test_result.result_type,
                     resp.probe_info_test_result.PASSED)

    # 7. Modifies D1 specific probed statement of Q3.
    qual_probe_info_3 = unittest_utils.LoadComponentProbeInfo('3-valid')
    probe_data = ps_storage_connector_inst.TryLoadOverriddenProbeData(
        qual_probe_info_3.component_identity.qual_id, 'device_one')
    probe_data.is_tested = False
    ps_storage_connector_inst.UpdateOverriddenProbeData(
        qual_probe_info_3.component_identity.qual_id, 'device_one', probe_data)

    # 8. Queries the probe status of Q1, Q2 and Q3 for D1.  The expected
    #    response shows Q1 and Q2 tested but not Q3.
    for comp_probe_info in comp_probe_infos:
      comp_probe_info.component_identity.device_id = 'device_one'
    req = stubby_pb2.GetProbeMetadataRequest(
        component_probe_infos=comp_probe_infos)
    resp = self._stubby_handler.GetProbeMetadata(req)
    self.assertEqual(
        [(m.probe_statement_type, m.is_tested) for m in resp.probe_metadatas],
        [
            (stubby_pb2.ProbeMetadata.QUAL_OVERRIDDEN, True),
            (stubby_pb2.ProbeMetadata.AUTO_GENERATED, True),
            (stubby_pb2.ProbeMetadata.DEVICE_OVERRIDDEN, False),
        ])


if __name__ == '__main__':
  unittest.main()
