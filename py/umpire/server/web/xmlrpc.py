# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Python twisted's module creates definition dynamically,
# pylint: disable=no-member

import logging
import time
import xmlrpc.client

from twisted.internet import defer
from twisted.python import failure
from twisted.python import reflect
from twisted.web import xmlrpc as twisted_xmlrpc


class XMLRPCContainer(twisted_xmlrpc.XMLRPC):
  """XMLRPC resource wrapper.

  This class binds RPC objects' methods to XML RPC call.

  Properties:
    handlers: Map remote procedure name to handler objects and functions.
  """

  def __init__(self):
    """Constructs Twisted twisted_xmlrpc.XMLRPC resource."""
    super(XMLRPCContainer, self).__init__(allowNone=True)
    self.handlers = {}

  def listProcedures(self):
    """Lists XMLRPC procedure names.

    Derived from twisted_xmlrpc.XMLRPC resource class. XMLRPC introspection
    calls this method to get list of procedure name string.
    """
    return list(self.handlers)

  # pylint: disable=arguments-differ
  def lookupProcedure(self, procedure_path):
    """Searches RPC procedure by name.

    Derived from twisted_xmlrpc.XMLRPC resource class. Twisted translates the
    XMLRPC to procedure call through this method.

    Args:
      procedure_path: procedure name string.

    Returns:
      Callable when function name is in the map. Or
      twisted_xmlrpc.NoSuchFunction(xmlrpc_code, message) when procedure not
      found.
    """
    # Let base class process sub-handlers.
    try:
      return super(XMLRPCContainer, self).lookupProcedure(procedure_path)
    except twisted_xmlrpc.NoSuchFunction:
      pass

    try:
      method = self.handlers[procedure_path]

      def _LogRPCCall(request, result, start_time):
        """Logs RPC request

        Args:
          request: Twisted request object.
          result: Returned value when calling the method.
          start_time: Time the method started.
        """
        error_message = ''
        if isinstance(result, failure.Failure):
          error_message = ': %s' % result.getTraceback()
        class_name = method.__self__.__class__.__name__
        method_name = method.__name__
        duration = time.time() - start_time
        logging.info('%s %s.%s [%.3f s]%s', request.getClientIP(),
                     class_name, method_name, duration, error_message)
        return result

      @twisted_xmlrpc.withRequest
      def _WrapProcedure(request, *args, **kwargs):
        """Catches and logs exception when calling RPC method.

        Returns:
          Procedure return value or twisted_xmlrpc.Fault when exception caught.
        """
        start_time = time.time()
        result = None
        if getattr(method, 'withRequest', False):
          result = defer.maybeDeferred(method, request, *args, **kwargs)
        else:
          result = defer.maybeDeferred(method, *args, **kwargs)
        result.addBoth(lambda result: _LogRPCCall(request, result, start_time))
        result.addErrback(lambda failure: twisted_xmlrpc.Fault(
            xmlrpc.client.APPLICATION_ERROR, failure.getTraceback()))
        return result

      return _WrapProcedure
    except KeyError:
      raise twisted_xmlrpc.NoSuchFunction(xmlrpc.client.METHOD_NOT_FOUND,
                                          procedure_path)

  def AddHandler(self, rpc_object):
    """Adds Umpire RPC object to this XMLRPC resource.

    Args:
      rpc_object: an UmpireRPC object.
    """
    for procedure in reflect.prefixedMethods(rpc_object):
      if callable(procedure) and getattr(procedure, 'is_rpc_method', False):
        procedure_path = procedure.__name__
        self.handlers[procedure_path] = procedure
        logging.debug('Add command handler %s', procedure_path)
