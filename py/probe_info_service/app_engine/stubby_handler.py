# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.probe_info_service.app_engine import probe_metainfo_connector
from cros.factory.probe_info_service.app_engine import probe_tool_manager
from cros.factory.probe_info_service.app_engine import protorpc_utils
from cros.factory.probe_info_service.app_engine import ps_storage_connector
# pylint: disable=no-name-in-module
from cros.factory.probe_info_service.app_engine import stubby_pb2
# pylint: enable=no-name-in-module


class ProbeInfoService(protorpc_utils.ProtoRPCServiceBase):
  SERVICE_DESCRIPTOR = stubby_pb2.DESCRIPTOR.services_by_name[
      'ProbeInfoService']

  def __init__(self):
    self._probe_tool_manager = probe_tool_manager.ProbeToolManager()
    self._probe_metainfo_connector = (
        probe_metainfo_connector.GetProbeMetaInfoConnectorInstance())
    self._ps_storage_connector = (
        ps_storage_connector.GetProbeStatementStorageConnector())

  @protorpc_utils.ProtoRPCServiceMethod
  def GetProbeSchema(self, request):
    del request  # unused
    response = stubby_pb2.GetProbeSchemaResponse()
    response.probe_schema.CopyFrom(self._probe_tool_manager.GetProbeSchema())
    return response

  @protorpc_utils.ProtoRPCServiceMethod
  def ValidateProbeInfo(self, request):
    response = stubby_pb2.ValidateProbeInfoResponse()
    response.probe_info_parsed_result.CopyFrom(
        self._probe_tool_manager.ValidateProbeInfo(request.probe_info,
                                                   not request.is_qual))
    return response

  @protorpc_utils.ProtoRPCServiceMethod
  def GetQualProbeTestBundle(self, request):
    response = stubby_pb2.GetQualProbeTestBundleResponse()

    probe_meta_info = self._probe_metainfo_connector.GetQualProbeMetaInfo(
        request.qual_probe_info.component_identity.qual_id)
    data_source = self._GetQualProbeDataSource(
        probe_meta_info, request.qual_probe_info)
    gen_result = self._probe_tool_manager.GenerateQualProbeTestBundlePayload(
        data_source)

    response.probe_info_parsed_result.CopyFrom(
        gen_result.probe_info_parsed_result)
    if gen_result.output is None:
      response.result_type = response.INVALID_PROBE_INFO
    else:
      response.result_type = response.SUCCEED
      response.test_bundle_payload = gen_result.output

    return response

  @protorpc_utils.ProtoRPCServiceMethod
  def UploadQualProbeTestResult(self, request):
    response = stubby_pb2.UploadQualProbeTestResultResponse()

    probe_meta_info = self._probe_metainfo_connector.GetQualProbeMetaInfo(
        request.qual_probe_info.component_identity.qual_id)
    data_source = self._GetQualProbeDataSource(
        probe_meta_info, request.qual_probe_info)

    try:
      result = self._probe_tool_manager.AnalyzeQualProbeTestResultPayload(
          data_source, request.test_result_payload)
    except probe_tool_manager.PayloadInvalidError as e:
      response.is_uploaded_payload_valid = False
      response.uploaded_payload_error_msg = str(e)
      return response

    if probe_meta_info.is_overridden:
      self._ps_storage_connector.MarkOverriddenQualProbeStatementTested(
          request.qual_probe_info.component_identity.qual_id)
    else:
      if result.result_type == result.PASSED:
        probe_meta_info.last_tested_probe_info_fp = data_source.fingerprint
        probe_meta_info.last_probe_info_fp_for_overridden = None
      elif result.result_type == result.INTRIVIAL_ERROR:
        probe_meta_info.last_probe_info_fp_for_overridden = (
            data_source.fingerprint)
      elif result.result_type == result.PROBE_PRAMETER_SUGGESTION:
        probe_meta_info.last_probe_info_fp_for_overridden = None
      self._probe_metainfo_connector.UpdateQualProbeMetaInfo(
          request.qual_probe_info.component_identity.qual_id, probe_meta_info)

    response.is_uploaded_payload_valid = True
    response.probe_info_test_result.CopyFrom(result)
    return response

  @protorpc_utils.ProtoRPCServiceMethod
  def CreateOverriddenProbeStatement(self, request):
    response = stubby_pb2.CreateOverriddenProbeStatementResponse()
    if request.component_probe_info.component_identity.device_id:
      # TODO(yhong): Create overridden probe statements for the specific device.
      raise NotImplementedError

    # Create overridden probe statement for the qualification.
    qual_probe_info = request.component_probe_info
    probe_meta_info = self._probe_metainfo_connector.GetQualProbeMetaInfo(
        qual_probe_info.component_identity.qual_id)
    if probe_meta_info.is_overridden:
      response.result_type = response.ALREADY_OVERRIDDEN_ERROR
      return response

    # Try to generate a default overridden probe statement from the given
    # probe info.
    data_source = self._probe_tool_manager.CreateProbeDataSource(
        self._GetComponentName(qual_probe_info.component_identity),
        qual_probe_info.probe_info)
    unused_pi_parsed_result, ps = (
        self._probe_tool_manager.DumpProbeDataSource(data_source))
    if ps is None:
      ps = self._probe_tool_manager.GenerateDummyProbeStatement(data_source)

    result_msg = self._ps_storage_connector.SetQualProbeStatementOverridden(
        qual_probe_info.component_identity.qual_id, ps)
    probe_meta_info.is_overridden = True
    self._probe_metainfo_connector.UpdateQualProbeMetaInfo(
        qual_probe_info.component_identity.qual_id, probe_meta_info)

    response.result_type = response.SUCCEED
    response.result_msg = result_msg
    return response

  @protorpc_utils.ProtoRPCServiceMethod
  def GetProbeMetadata(self, request):
    response = stubby_pb2.GetProbeMetadataResponse()

    for comp_probe_info in request.component_probe_infos:
      if comp_probe_info.component_identity.device_id:
        # TODO(yhong): Load the status of a device specific overridden probe
        #     statement.
        raise NotImplementedError

      metainfo = self._probe_metainfo_connector.GetQualProbeMetaInfo(
          comp_probe_info.component_identity.qual_id)
      if metainfo.is_overridden:
        probe_data = self._ps_storage_connector.LoadOverriddenQualProbeData(
            comp_probe_info.component_identity.qual_id)
        response.probe_metadatas.add(
            is_overridden=True, is_tested=probe_data.is_tested)
      else:
        data_src = self._probe_tool_manager.CreateProbeDataSource(
            self._GetComponentName(comp_probe_info.component_identity),
            comp_probe_info.probe_info)
        fp = data_src.fingerprint
        response.probe_metadatas.add(
            is_tested=metainfo.last_tested_probe_info_fp == fp,
            is_proved_ready_for_overridden=(
                metainfo.last_probe_info_fp_for_overridden == fp))

    return response

  def _GetComponentName(self, component_identity):
    return 'AVL_%d-%s-%s' % (component_identity.qual_id,
                             component_identity.device_id,
                             component_identity.readable_label)

  def _GetQualProbeDataSource(self, probe_meta_info, qual_probe_info):
    if probe_meta_info.is_overridden:
      probe_data = self._ps_storage_connector.LoadOverriddenQualProbeData(
          qual_probe_info.component_identity.qual_id)
      return self._probe_tool_manager.LoadProbeDataSource(
          probe_data.probe_statement)

    return self._probe_tool_manager.CreateProbeDataSource(
        self._GetComponentName(qual_probe_info.component_identity),
        qual_probe_info.probe_info)
