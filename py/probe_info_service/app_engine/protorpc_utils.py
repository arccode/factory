# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import uuid

# pylint: disable=import-error,no-name-in-module
import flask
from google.protobuf import symbol_database


class ProtoRPCServiceBase(object):
  """Base class of a ProtoRPC Service.

  Sub-class must override `SERVICE_DESCRIPTOR` to the correct descriptor
  instance.  To implement the service's methods, author should define class
  methods with the same names.  The method will be called with only one argument
  in type of the request message defined in the protobuf file, and the return
  value should be in type of the response message defined in the protobuf file
  as well.
  """
  SERVICE_DESCRIPTOR = None


class _ProtoRPCServiceFlaskAppViewFunc(object):
  """A helper class to handle ProtoRPC POST requests on flask apps."""

  def __init__(self, service_inst):
    self._service_inst = service_inst
    self._method_msg_classes = {}

    sym_db = symbol_database.Default()
    for method_desc in self._service_inst.SERVICE_DESCRIPTOR.methods:
      self._method_msg_classes[method_desc.name] = (
          sym_db.GetSymbol(method_desc.input_type.full_name),
          sym_db.GetSymbol(method_desc.output_type.full_name))

  def __call__(self, method_name):
    msg_classes = self._method_msg_classes.get(method_name)
    if not msg_classes:
      return flask.Response(status=404)
    request_msg_class, response_msg_class = msg_classes
    try:
      request_msg = request_msg_class.FromString(flask.request.get_data())
      method = getattr(self._service_inst, method_name)
      response_msg = method(request_msg)
      assert isinstance(response_msg, response_msg_class)
      response_raw_body = response_msg.SerializeToString()
    except Exception:
      return flask.Response(status=500)
    response = flask.Response(response=response_raw_body)
    response.headers['Content-type'] = 'application/octet-stream'
    return response


def RegisterProtoRPCServiceToFlaskApp(
    app_inst, path, service_inst, service_name=None):
  """Register the given ProtoRPC service to the given flask app.

  Args:
    app_inst: Instance of `flask.Flask`.
    path: Root URL of the service.
    service_inst: The ProtoRPC service to register, must be a subclass of
        `ProtoRPCServiceBase`.
    service_name: Specify the name of the service.  Default to
        `service_inst.SERVICE_DESCRIPTOR.name`.
  """
  service_name = service_name or service_inst.SERVICE_DESCRIPTOR.name
  endpoint_name = '__protorpc_service_view_func_' + str(uuid.uuid1())
  view_func = _ProtoRPCServiceFlaskAppViewFunc(service_inst)
  app_inst.add_url_rule(
      '%s/%s.<method_name>' % (path, service_name), endpoint=endpoint_name,
      view_func=view_func, methods=['POST'])
