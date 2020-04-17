# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=no-name-in-module
from cros.factory.probe_info_service.app_engine import probe_tool_manager
from cros.factory.probe_info_service.app_engine import protorpc_utils
from cros.factory.probe_info_service.app_engine import stubby_pb2


class ProbeInfoService(protorpc_utils.ProtoRPCServiceBase):
  SERVICE_DESCRIPTOR = stubby_pb2.DESCRIPTOR.services_by_name[
      'ProbeInfoService']

  def __init__(self):
    self._probe_tool_manager = probe_tool_manager.ProbeToolManager()

  @protorpc_utils.ProtoRPCServiceMethod
  def GetProbeSchema(self, get_probe_schema_request):
    del get_probe_schema_request
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
