# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import functools
import typing

from cros.factory.probe_info_service.app_engine import probe_metainfo_connector
from cros.factory.probe_info_service.app_engine import probe_tool_manager
from cros.factory.probe_info_service.app_engine import protorpc_utils
from cros.factory.probe_info_service.app_engine import ps_storage_connector
# pylint: disable=no-name-in-module
from cros.factory.probe_info_service.app_engine import stubby_pb2
# pylint: enable=no-name-in-module


def GetProbeDataSourceComponentName(component_identity):
  return 'AVL_%d' % component_identity.qual_id


class _ProbeDataSourceFactory(typing.NamedTuple):
  probe_statement_type: int
  probe_data_source_generator: typing.Callable[
      [], probe_tool_manager.ProbeDataSource]
  overridden_probe_data: typing.Optional[
      ps_storage_connector.OverriddenProbeData]


class ProbeInfoService(protorpc_utils.ProtoRPCServiceBase):
  SERVICE_DESCRIPTOR = stubby_pb2.DESCRIPTOR.services_by_name[
      'ProbeInfoService']

  MSG_NO_PROBE_STATEMENT_PREVIEW_INVALID_AVL_DATA = (
      '(no preview available due to the invalid data from AVL)')

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
  def ValidateProbeInfo(self, request: stubby_pb2.ValidateProbeInfoRequest):
    response = stubby_pb2.ValidateProbeInfoResponse()
    response.probe_info_parsed_result.CopyFrom(
        self._probe_tool_manager.ValidateProbeInfo(request.probe_info,
                                                   not request.is_qual))
    return response

  @protorpc_utils.ProtoRPCServiceMethod
  def GetQualProbeTestBundle(
      self, request: stubby_pb2.GetQualProbeTestBundleRequest):
    response = stubby_pb2.GetQualProbeTestBundleResponse()

    probe_data_source_factory = self._GetQualProbeDataSourceFactory(
        request.qual_probe_info)
    gen_result = self._probe_tool_manager.GenerateProbeBundlePayload([
        probe_data_source_factory.probe_data_source_generator()])

    response.probe_info_parsed_result.CopyFrom(
        gen_result.probe_info_parsed_results[0])
    if gen_result.output is None:
      response.status = response.INVALID_PROBE_INFO
    else:
      response.status = response.SUCCEED
      response.test_bundle_payload = gen_result.output.content
      response.test_bundle_file_name = gen_result.output.name

    return response

  @protorpc_utils.ProtoRPCServiceMethod
  def UploadQualProbeTestResult(
      self, request: stubby_pb2.UploadQualProbeTestResultRequest):
    response = stubby_pb2.UploadQualProbeTestResultResponse()

    probe_data_source_factory = self._GetQualProbeDataSourceFactory(
        request.qual_probe_info)
    data_source = probe_data_source_factory.probe_data_source_generator()

    try:
      result = self._probe_tool_manager.AnalyzeQualProbeTestResultPayload(
          data_source, request.test_result_payload)
    except probe_tool_manager.PayloadInvalidError as e:
      response.is_uploaded_payload_valid = False
      response.uploaded_payload_error_msg = str(e)
      return response

    if (probe_data_source_factory.probe_statement_type
        != stubby_pb2.ProbeMetadata.AUTO_GENERATED):
      if result.result_type == result.PASSED:
        self._ps_storage_connector.MarkOverriddenProbeStatementTested(
            request.qual_probe_info.component_identity.qual_id, '')
    else:
      probe_meta_info = self._probe_metainfo_connector.GetQualProbeMetaInfo(
          request.qual_probe_info.component_identity.qual_id)
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
  def GetDeviceProbeConfig(
      self, request: stubby_pb2.GetDeviceProbeConfigRequest):
    response = stubby_pb2.GetDeviceProbeConfigResponse()

    probe_data_sources = []
    for comp_probe_info in request.component_probe_infos:
      probe_data_source_factory = self._GetProbeDataSourceFactory(
          comp_probe_info)
      probe_data_sources.append(
          probe_data_source_factory.probe_data_source_generator())

    gen_result = self._probe_tool_manager.GenerateProbeBundlePayload(
        probe_data_sources)

    for pi_parsed_result in gen_result.probe_info_parsed_results:
      response.probe_info_parsed_results.append(pi_parsed_result)
    if gen_result.output is None:
      response.status = response.INVALID_PROBE_INFO
    else:
      response.status = response.SUCCEED
      response.generated_config_payload = gen_result.output.content
      response.generated_config_file_name = gen_result.output.name

    return response

  @protorpc_utils.ProtoRPCServiceMethod
  def UploadDeviceProbeResult(
      self, request: stubby_pb2.UploadDeviceProbeResultRequest):
    response = stubby_pb2.UploadDeviceProbeResultResponse()

    probe_data_source_factories = [
        self._GetProbeDataSourceFactory(comp_probe_info)
        for comp_probe_info in request.component_probe_infos]
    probe_data_sources = [
        f.probe_data_source_generator() for f in probe_data_source_factories]

    try:
      analyzed_result = (
          self._probe_tool_manager.AnalyzeDeviceProbeResultPayload(
              probe_data_sources, request.probe_result_payload))
    except probe_tool_manager.PayloadInvalidError as e:
      response.upload_status = response.PAYLOAD_INVALID_ERROR
      response.error_msg = str(e)
      return response

    if analyzed_result.intrivial_error_msg:
      response.upload_status = response.INTRIVIAL_ERROR
      response.error_msg = analyzed_result.intrivial_error_msg
      return response

    for i, probe_data_source_factory in enumerate(probe_data_source_factories):
      if (analyzed_result.probe_info_test_results[i].result_type
          == stubby_pb2.ProbeInfoParsedResult.PASSED):
        ps_type = probe_data_source_factory.probe_statement_type
        qual_id = request.component_probe_infos[i].component_identity.qual_id
        device_id = request.component_probe_infos[
            i].component_identity.device_id
        if ps_type == stubby_pb2.ProbeMetadata.AUTO_GENERATED:
          probe_meta_info = self._probe_metainfo_connector.GetQualProbeMetaInfo(
              qual_id)
          probe_meta_info.last_tested_probe_info_fp = (
              probe_data_sources[i].fingerprint)
          self._probe_metainfo_connector.UpdateQualProbeMetaInfo(
              qual_id, probe_meta_info)
        else:
          if ps_type == stubby_pb2.ProbeMetadata.QUAL_OVERRIDDEN:
            device_id = ''
          probe_data_source_factory.overridden_probe_data.is_tested = True
          self._ps_storage_connector.MarkOverriddenProbeStatementTested(
              qual_id, device_id)

    response.upload_status = response.SUCCEED
    response.probe_info_test_results.extend(
        analyzed_result.probe_info_test_results)
    return response

  @protorpc_utils.ProtoRPCServiceMethod
  def CreateOverriddenProbeStatement(
      self, request: stubby_pb2.CreateOverriddenProbeStatementRequest):
    response = stubby_pb2.CreateOverriddenProbeStatementResponse()

    comp_identity = request.component_probe_info.component_identity
    probe_info = request.component_probe_info.probe_info

    if self._ps_storage_connector.TryLoadOverriddenProbeData(
        comp_identity.qual_id, comp_identity.device_id):
      response.status = response.ALREADY_OVERRIDDEN_ERROR
      return response

    # Try to generate a default overridden probe statement from the given
    # probe info.
    data_source = self._probe_tool_manager.CreateProbeDataSource(
        GetProbeDataSourceComponentName(comp_identity), probe_info)
    unused_pi_parsed_result, ps = (
        self._probe_tool_manager.DumpProbeDataSource(data_source))
    if ps is None:
      ps = self._probe_tool_manager.GenerateDummyProbeStatement(data_source)

    result_msg = self._ps_storage_connector.SetProbeStatementOverridden(
        comp_identity.qual_id, comp_identity.device_id, ps)

    response.status = response.SUCCEED
    response.result_msg = result_msg
    return response

  @protorpc_utils.ProtoRPCServiceMethod
  def GetProbeMetadata(self, request: stubby_pb2.GetProbeMetadataRequest):
    response = stubby_pb2.GetProbeMetadataResponse()

    for comp_probe_info in request.component_probe_infos:
      probe_data_source_factory = self._GetProbeDataSourceFactory(
          comp_probe_info)
      if (probe_data_source_factory.probe_statement_type !=
          stubby_pb2.ProbeMetadata.AUTO_GENERATED):
        probe_metadata = response.probe_metadatas.add(
            probe_statement_type=probe_data_source_factory.probe_statement_type,
            is_tested=probe_data_source_factory.overridden_probe_data.is_tested)
        if request.include_probe_statement_preview:
          data_src = probe_data_source_factory.probe_data_source_generator()

      else:
        qual_metainfo = self._probe_metainfo_connector.GetQualProbeMetaInfo(
            comp_probe_info.component_identity.qual_id)
        data_src = self._probe_tool_manager.CreateProbeDataSource(
            GetProbeDataSourceComponentName(comp_probe_info.component_identity),
            comp_probe_info.probe_info)
        fp = data_src.fingerprint
        probe_metadata = response.probe_metadatas.add(
            probe_statement_type=stubby_pb2.ProbeMetadata.AUTO_GENERATED,
            is_tested=qual_metainfo.last_tested_probe_info_fp == fp,
            is_proved_ready_for_overridden=(
                qual_metainfo.last_probe_info_fp_for_overridden == fp))

      if request.include_probe_statement_preview:
        gen_result = self._probe_tool_manager.GenerateRawProbeStatement(
            data_src)
        probe_metadata.probe_statement_preview = (
            gen_result.output if gen_result.output is not None else
            self.MSG_NO_PROBE_STATEMENT_PREVIEW_INVALID_AVL_DATA)

    return response

  def _GetQualProbeDataSourceFactory(self, qual_probe_info):
    component_name = GetProbeDataSourceComponentName(
        qual_probe_info.component_identity)
    ret = self._TryGetProbeDataSourceFactoryForOverridden(
        qual_probe_info.component_identity.qual_id, '',
        stubby_pb2.ProbeMetadata.QUAL_OVERRIDDEN, component_name)
    if ret:
      return ret

    return _ProbeDataSourceFactory(
        stubby_pb2.ProbeMetadata.AUTO_GENERATED,
        functools.partial(self._probe_tool_manager.CreateProbeDataSource,
                          component_name, qual_probe_info.probe_info),
        None)

  def _GetProbeDataSourceFactory(self, comp_probe_info):
    component_name = GetProbeDataSourceComponentName(
        comp_probe_info.component_identity)
    qual_id = comp_probe_info.component_identity.qual_id
    device_id = comp_probe_info.component_identity.device_id
    if device_id:
      ret = self._TryGetProbeDataSourceFactoryForOverridden(
          qual_id, device_id, stubby_pb2.ProbeMetadata.DEVICE_OVERRIDDEN,
          component_name)
      if ret:
        return ret
    return self._GetQualProbeDataSourceFactory(comp_probe_info)

  def _TryGetProbeDataSourceFactoryForOverridden(
      self, qual_id, device_id, probe_statement_type, component_name):
    probe_data = self._ps_storage_connector.TryLoadOverriddenProbeData(
        qual_id, device_id)
    if not probe_data:
      return None
    return _ProbeDataSourceFactory(
        probe_statement_type,
        functools.partial(self._probe_tool_manager.LoadProbeDataSource,
                          component_name, probe_data.probe_statement),
        probe_data)
