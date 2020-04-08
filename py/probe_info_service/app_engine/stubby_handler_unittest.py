# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

from google.protobuf import text_format

from cros.factory.probe_info_service.app_engine import probe_metainfo_connector
from cros.factory.probe_info_service.app_engine import stubby_handler
# pylint: disable=no-name-in-module
from cros.factory.probe_info_service.app_engine import stubby_pb2
# pylint: enable=no-name-in-module
from cros.factory.utils import file_utils


TESTDATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), 'testdata')

SEPARATOR_TAG = '### SEPARATOR ###'


class StubbyHandlerTest(unittest.TestCase):
  def setUp(self):
    inst = probe_metainfo_connector.GetProbeMetaInfoConnectorInstance()
    inst.Clean()

    self._stubby_handler = stubby_handler.ProbeInfoService()

  def testGetProbeSchema(self):
    # This API is stateless, so just simply verify the call stack.
    req = stubby_pb2.GetProbeSchemaRequest()
    resp = self._stubby_handler.GetProbeSchema(req)
    self.assertCountEqual(
        [f.name for f in resp.probe_schema.probe_function_definitions],
        ['battery.generic_battery', 'storage.mmc_storage',
         'storage.nvme_storage'])

  def testScenario1(self):
    testdata = self._LoadScenarioBundle('scenario1')

    # 1. The user validates the probe info and finds format error.
    req = stubby_pb2.ValidateProbeInfoRequest()
    text_format.Parse(testdata[0], req)
    resp = self._stubby_handler.ValidateProbeInfo(req)
    self.assertEqual(resp.probe_info_parsed_result.result_type,
                     resp.probe_info_parsed_result.PROBE_PARAMETER_ERROR)

    # 2. After probe info fixup, the user creates a qual test bundle.
    req = stubby_pb2.GetQualProbeTestBundleRequest()
    text_format.Parse(testdata[1], req)
    resp = self._stubby_handler.GetQualProbeTestBundle(req)
    self.assertEqual(resp.result_type, resp.SUCCEED)
    qual_probe_info1 = req.qual_probe_info

    # 3. The user gets a differnet test bundle from a different probe info.
    req = stubby_pb2.GetQualProbeTestBundleRequest()
    text_format.Parse(testdata[2], req)
    resp = self._stubby_handler.GetQualProbeTestBundle(req)
    self.assertEqual(resp.result_type, resp.SUCCEED)
    qual_probe_info2 = req.qual_probe_info

    # 4. The user uploads a positive result for the first bundle, get "LEGACY"
    #    notification.
    req = stubby_pb2.UploadQualProbeTestResultRequest()
    req.qual_probe_info.CopyFrom(qual_probe_info2)
    req.test_result_payload = testdata[3].encode('utf-8')
    resp = self._stubby_handler.UploadQualProbeTestResult(req)
    self.assertTrue(resp.is_uploaded_payload_valid)
    self.assertEqual(resp.probe_info_test_result.result_type,
                     resp.probe_info_test_result.LEGACY)

    req = stubby_pb2.GetProbeMetadataRequest(
        component_probe_infos=[qual_probe_info2])
    resp = self._stubby_handler.GetProbeMetadata(req)
    self.assertFalse(resp.probe_metadatas[0].is_tested)

    # 5. The user then uploads the second positive test bundle and get
    #    "PASSED".  Now the qual probe info become "tested".
    req = stubby_pb2.UploadQualProbeTestResultRequest()
    req.qual_probe_info.CopyFrom(qual_probe_info2)
    req.test_result_payload = testdata[4].encode('utf-8')
    resp = self._stubby_handler.UploadQualProbeTestResult(req)
    self.assertTrue(resp.is_uploaded_payload_valid)
    self.assertEqual(resp.probe_info_test_result.result_type,
                     resp.probe_info_test_result.PASSED)

    req = stubby_pb2.GetProbeMetadataRequest(
        component_probe_infos=[qual_probe_info2])
    resp = self._stubby_handler.GetProbeMetadata(req)
    self.assertTrue(resp.probe_metadatas[0].is_tested)

    # 6. The user modifies the probe info again.  Now the qual probe info
    #    becomes "untested" again.
    req = stubby_pb2.GetProbeMetadataRequest(
        component_probe_infos=[qual_probe_info1])
    resp = self._stubby_handler.GetProbeMetadata(req)
    self.assertFalse(resp.probe_metadatas[0].is_tested)

  def _LoadScenarioBundle(self, scenario_name):
    filepath = os.path.join(
        TESTDATA_DIR, 'stubby_handler_%s.text' % scenario_name)
    return file_utils.ReadFile(filepath).split(SEPARATOR_TAG)


if __name__ == '__main__':
  unittest.main()
