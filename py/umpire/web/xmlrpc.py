# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Python twisted's module creates definition dynamically, pylint: disable=E1101

import logging
import traceback
from twisted.python import reflect
from twisted.web import xmlrpc
from twisted.web.xmlrpc import withRequest
import xmlrpclib


class XMLRPCContainer(xmlrpc.XMLRPC):

  """XMLRPC resource wrapper.

  This class binds RPC objects' methods to XML RPC call.

  Properties:
    handlers: Map remote procedure name to handler objects and functions.
  """

  def __init__(self):
    """Constructs Twisted xmlrpc.XMLRPC resource.

    Twisted XMLRPC is old-style class. The allowNone=True needs to be passed
    to parent ctor in old-style way.
    """
    xmlrpc.XMLRPC.__init__(self, allowNone=True)
    self.handlers = {}

  def listProcedures(self):
    """Lists XMLRPC procedure names.

    Derived from xmlrpc.XMLRPC resource class. XMLRPC introspection calls
    this method to get list of procedure name string.
    """
    return self.handlers.keys()

  def lookupProcedure(self, procedure_path):
    """Searches RPC procedure by name.

    Derived from xmlrpc.XMLRPC resource class. Twisted translates the XMLRPC
    to procedure call through this method.

    Args:
      procedure_path: procedure name string.

    Returns:
      Callable when function name is in the map. Or
      xmlrpc.NoSuchFunction(xmlrpc_code, message) when procedure not found.
    """
    # Let base class process sub-handlers.
    try:
      # xmlrpc.XMLRPC is old-style Python class. Cannot use super().
      return xmlrpc.XMLRPC.lookupProcedure(self, procedure_path)
    except xmlrpc.NoSuchFunction:
      pass

    try:
      method = self.handlers[procedure_path]

      @withRequest
      def _WrapProcedure(request, *args, **kwargs):
        """Catches exception when calling RPC function.

        Returns:
          Procedure return value or xmlrpc.Fault when exception caught.
        """
        try:
          if getattr(method, 'withRequest', False):
            return method(request, *args, **kwargs)
          else:
            return method(*args, **kwargs)
        except Exception:
          logging.exception('%s raises', procedure_path)
          return xmlrpc.Fault(xmlrpclib.APPLICATION_ERROR,
                              traceback.format_exc())

      return _WrapProcedure
    except KeyError:
      raise xmlrpc.NoSuchFunction(xmlrpclib.METHOD_NOT_FOUND, procedure_path)

  def AddHandler(self, rpc_object):
    """Adds Umpire RPC object to this XMLRPC resource.

    Args:
      rpc_object: Umpire RPC object.
    """
    for procedure in reflect.prefixedMethods(rpc_object):
      if not callable(procedure):
        continue
      if not hasattr(procedure, 'is_rpc_method'):
        continue
      if procedure.is_rpc_method:
        procedure_path = procedure.__name__
        self.handlers[procedure_path] = procedure
        logging.debug('Add command handler %s', procedure_path)
