# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import enum
import http
import logging
import uuid

# pylint: disable=wrong-import-order
import flask
from google.protobuf import symbol_database

# pylint: enable=wrong-import-order


# Referenced from https://grpc.github.io/grpc/core/md_doc_statuscodes.html
class RPCCanonicalErrorCode(enum.Enum):
  PERMISSION_DENIED = (7, http.HTTPStatus.FORBIDDEN)
  INTERNAL = (13, http.HTTPStatus.INTERNAL_SERVER_ERROR)
  NOT_FOUND = (5, http.HTTPStatus.NOT_FOUND)
  FAILED_PRECONDITION = (9, http.HTTPStatus.BAD_REQUEST)
  ABORTED = (10, http.HTTPStatus.CONFLICT)
  UNIMPLEMENTED = (12, http.HTTPStatus.NOT_IMPLEMENTED)


class ProtoRPCException(Exception):
  """RPC exceptions with addition information to set error status/code in stubby
  requests."""

  def __init__(self, code, detail=None):
    super(ProtoRPCException, self).__init__()
    self.code = code
    self.detail = detail


class _ProtoRPCServiceBaseMeta(type):
  """Metaclass for ProtoRPC classes.

  This metaclass customizes class creation flow to parse and convert the
  service descriptor object into a friendly data structure for information
  looking up in runtime.
  """

  # pylint: disable=return-in-init
  def __init__(cls, name, bases, attrs, **kwargs):
    service_descriptor = attrs.get('SERVICE_DESCRIPTOR')
    if service_descriptor:
      sym_db = symbol_database.Default()
      for method_desc in service_descriptor.methods:
        method = getattr(cls, method_desc.name, None)
        rpc_method_spec = getattr(method, 'rpc_method_spec', None)
        if rpc_method_spec:
          rpc_method_spec.request_type = sym_db.GetSymbol(
              method_desc.input_type.full_name)
          rpc_method_spec.response_type = sym_db.GetSymbol(
              method_desc.output_type.full_name)
    return super().__init__(name, bases, attrs, **kwargs)


class ProtoRPCServiceBase(metaclass=_ProtoRPCServiceBaseMeta):
  """Base class of a ProtoRPC Service.

  Sub-class must override `SERVICE_DESCRIPTOR` to the correct descriptor
  instance.  To implement the service's methods, author should define class
  methods with the same names and decorates it with `ProtoRPCServiceMethod`.
  The method will be called with only one argument in type of the request
  message defined in the protobuf file, and the return value should be in
  type of the response message defined in the protobuf file as well.
  """
  SERVICE_DESCRIPTOR = None


class _ProtoRPCServiceMethodSpec:
  """Placeholder for spec of a ProtoRPC method."""

  def __init__(self, request_type, response_type):
    self.request_type = request_type
    self.response_type = response_type


def ProtoRPCServiceMethod(method):
  """Decorator for ProtoRPC methods.

  It wraps the target method with type-checking assertions as well as attaching
  additional a spec information placeholder.
  """

  def wrapper(self, request):
    assert isinstance(request, wrapper.rpc_method_spec.request_type)
    logging.info("Request:\n%s", request)
    response = method(self, request)
    assert isinstance(response, wrapper.rpc_method_spec.response_type)
    logging.info("Response:\n%s", response)
    return response

  # Since the service's descriptor will be parsed when the class is created,
  # which is later than the invocation time of this decorator, here it just
  # place the placeholder with dummy contents.
  wrapper.rpc_method_spec = _ProtoRPCServiceMethodSpec(None, None)
  return wrapper


class _ProtoRPCServiceFlaskAppViewFunc:
  """A helper class to handle ProtoRPC POST requests on flask apps."""

  def __init__(self, service_inst):
    self._service_inst = service_inst

  def __call__(self, method_name):
    method = getattr(self._service_inst, method_name, None)
    rpc_method_spec = getattr(method, 'rpc_method_spec', None)
    if not rpc_method_spec:
      return flask.Response(status=404)

    try:
      request_msg = rpc_method_spec.request_type.FromString(
          flask.request.get_data())
      response_msg = method(request_msg)
      response_raw_body = response_msg.SerializeToString()
    except ProtoRPCException as ex:
      rpc_code, http_code = ex.code.value
      resp = flask.Response(status=http_code)
      resp.headers['RPC-Canonical-Code'] = rpc_code
      if ex.detail:
        resp.headers['RPC-Error-Detail'] = ex.detail
      return resp
    except Exception:
      logging.exception('Caught exception from RPC method %r.', method_name)
      return flask.Response(status=http.HTTPStatus.INTERNAL_SERVER_ERROR)

    response = flask.Response(response=response_raw_body)
    response.headers['Content-type'] = 'application/octet-stream'
    return response


def RegisterProtoRPCServiceToFlaskApp(app_inst, path, service_inst,
                                      service_name=None):
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
  app_inst.add_url_rule('%s/%s.<method_name>' % (path, service_name),
                        endpoint=endpoint_name, view_func=view_func,
                        methods=['POST'])
