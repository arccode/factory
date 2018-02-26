# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Proxy requests to HWID Service on Kubernetes Engine."""

from xmlrpclib import ServerProxy

# pylint: disable=import-error, no-name-in-module
from protorpc import remote
from protorpc.wsgi import service

import config # pylint: disable=import-error
import definition as _def


HWIDSERVICEPROXY_PATH = '/_ah/stubby/HwidService.*'


class HWIDServiceProxy(remote.Service):  # pylint: disable=no-init
  def __init__(self):
    """Constructor."""
    self.proxy = ServerProxy(config.GKE_HWID_SERVICE_URL)

  @remote.method(_def.ValidateConfigRequest, _def.ValidateConfigResponse)
  def ValidateConfig(self, request):
    """A RPC function for validating HWID config including checksum check.

    Args:
      request: A ValidateConfigRequest object.

    Retruns:
      A ValidateConfigResponse object.
    """
    response = self.proxy.ValidateConfig(request.hwid)
    if response['success']:
      return _def.ValidateConfigResponse(err_code=_def.ErrorCode.NO_ERROR)
    else:
      return _def.ValidateConfigResponse(
          err_code=_def.ErrorCode.VALIDATION_ERROR, err_msg=response['ret'])

  @remote.method(_def.ValidateConfigAndUpdateChecksumResquest,
                 _def.ValidateConfigAndUpdateChecksumResponse)
  def ValidateConfigAndUpdateChecksum(self, request):
    """A RPC function for validating and updating new HWID config

    Args:
      request: A ValidateConfigAndUpdateChecksumResquest object.

    Retruns:
      A ValidateConfigAndUpdateChecksumResponse object.

    """
    response = self.proxy.ValidateConfigAndUpdateChecksum(
        request.new_hwid, request.old_hwid)
    if response['success']:
      return _def.ValidateConfigAndUpdateChecksumResponse(
          err_code=_def.ErrorCode.NO_ERROR, hwid=response['ret'])
    else:
      return _def.ValidateConfigAndUpdateChecksumResponse(
          err_code=_def.ErrorCode.VALIDATION_ERROR, err_msg=response['ret'])


app = service.service_mappings([(HWIDSERVICEPROXY_PATH, HWIDServiceProxy)])
