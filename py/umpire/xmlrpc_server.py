# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""XMLRPCServer: Starts a XMLRPC service that handles XML RPC.

XMLRPCServer accepts a class instance and registers methods with @RPCCall
decorated as XMLRPC methods.

Example:

  class DummyService(object):
    @RPCCall
    def Echo(self, msg):
      logging.debug('Echo(%s) called', msg)
      return msg

  service = DummyService()
  # Run forever.
  XMLRPCServer(address='127.0.0.1', port=9998, instance=service)
"""

from twisted.internet import reactor
from twisted.web import server
from twisted.web import wsgi
import logging
import re
import SimpleXMLRPCServer
import sys
import time
import traceback

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.web import wsgi as umpire_wsgi
from cros.factory.umpire import shop_floor_handler


def XMLRPCServer(address, port, instance, script_name=None, path_info=None):
  """Starts an XMLRPC service that handles XML-RPC at given address:port.

  It scans methods in the given instance and registers the ones with
  @RPCCall decorated as XMLRPC methods. It uses flup WSGIServer as XMLRPC
  server with wrapped application based on the instance.

  It runs forever.

  Args:
    address: IP address to bind.
    port: Port for server to listen.
    instance: Server instance to handle XML RPC requests.
    script_name: If specified, only accept requests in which their
        SCRIPT_NAME environ matches the regular expression.
    path_info: If specified, only accept requests in which their
        PATH_INFO environ matches the regular expression.
  """
  application = MyXMLRPCApp(instance, script_name=script_name,
                            path_info=path_info)
  rpc_resource = wsgi.WSGIResource(reactor, reactor.getThreadPool(),
                                   application)

  logging.info('Running XMLRPC service at %s:%d for class %s',
               address, port, instance.__class__.__name__)
  rpc_site = server.Site(rpc_resource)
  # Listen to rpc server port.
  reactor.listenTCP(port, rpc_site, interface=address)
  reactor.run()



class SessionMediator(object):
  """Encapsulator of session and dispatcher.

  It holds two objects, WSGI session and XMLRPC dispatcher. The RPC method and
  exception are written back to session dictionary.

  It provides MarshaledDispatch, which records calling method and its
  parameters before invoking method and also records exception if any.

  The recorded method, parameters and exception are used for logging.
  """
  XMLRPC_METHOD = 'xmlrpc_method'
  XMLPRC_PARAMS = 'xmlrpc_params'
  XMLRPC_EXCEPTION = 'xmlrpc_exception'

  def __init__(self, session, dispatcher):
    """Constructor. Holds session and dispatcher.

    Also adds 'xmlrpc_method', 'xmlrpc_params' and 'xmlrpc_exception' keys
    into session.

    Args:
      session: WSGI session object
      dispatcher: XMLRPCDispatcher object
    """
    self.session = session
    self.dispatcher = dispatcher
    self.session[self.XMLRPC_METHOD] = ''
    self.session[self.XMLPRC_PARAMS] = None
    self.session[self.XMLRPC_EXCEPTION] = None

  def MarshaledDispatch(self, data):
    """Dispatches request and records method and parameters being called.

    It records method and its parameters (in request data) being called and
    records exception if any.
    """
    return self.dispatcher._marshaled_dispatch(  # pylint: disable=W0212
        data, getattr(self, '_Dispatch', None)) + '\n'

  def _Dispatch(self, method, params):
    try:
      self.session[self.XMLRPC_METHOD] = method
      self.session[self.XMLPRC_PARAMS] = params
      return self.dispatcher._dispatch(method, params)  # pylint: disable=W0212
    except:  # pylint: disable=W0702
      # Formats the current exception string.
      # Copied from py.utils.debug_utils.FormatExceptionOnly().
      self.session[self.XMLRPC_EXCEPTION] = '\n'.join(
          traceback.format_exception_only(*sys.exc_info()[:2])).strip()
      raise


class MyXMLRPCApp(object):
  """WSGI to XMLRPC callable app.

  Used to register class instance's methods into XMLRPC dispatcher and
  provides __call__ interface for WSGI server to call.

  It also checks incoming WSGI environ's SCRIPT_NAME and PATH_INFO if
  script_name or path_info parameters are assigned in constructor.
  """
  _MAX_CHUNK_SIZE = 10 * 1024 * 1024

  def __init__(self, instance, script_name=None, path_info=None):
    """Creates XML RPC dispatcher and registers methods.

    Args:
      instance: An instance of XMLRPC module. Only registers methods decorated
          by RPCCall.
      script_name: If specified, only accept requests in which their
          SCRIPT_NAME environ matches the regular expression.
      path_info: If specified, only accept requests in which their
          PATH_INFO environ matches the regular expression.
    """
    self.dispatcher = SimpleXMLRPCServer.SimpleXMLRPCDispatcher(
        allow_none=True, encoding=None)
    self.dispatcher.register_introspection_functions()
    if instance is not None:
      self.RegisterInstance(instance)
    self._script_name = script_name
    self._path_info = path_info

  def __call__(self, environ, start_response):
    """Invokes XMLRPC method and returns response.

    If request is not a POST, returns '400 Bad Request'.
    If request's SCRIPT_NAME or PATH_INFO mismatch, returns '410 Gone'.

    Args:
      environ: WSGI environment dictionary.
      start_response: WSGI response functor for sending HTTP headers.
    """
    session = umpire_wsgi.WSGISession(environ, start_response)
    if session.REQUEST_METHOD != 'POST':
      return session.BadRequest400()

    if not self.MatchPath(environ):
      return session.Gone410()

    return self._XMLRPCCall(session)

  def MatchPath(self, environ):
    """Checks if environ's SCRIPT_NAME and PATH_INFO matches.

    Args:
      environ: WSGI environment dictionary.

    Returns:
      True if environ's SCRIPT_NAME and PATH_INFO matches the regular expression
      specified in constructor.
    """
    return ((not self._script_name or
             re.match(self._script_name, environ['SCRIPT_NAME'])) and
            (not self._path_info or
             re.match(self._path_info, environ['PATH_INFO'])))

  def RegisterInstance(self, instance):
    """Registers methods in given class instance.

    Only registers methods decorated by RPCCall, i.e. method has is_rpc_method
    attribute and is set to True.

    Args:
      instance: class instance that holds methods to be registered.
    """
    for method_name in SimpleXMLRPCServer.list_public_methods(instance):
      method = getattr(instance, method_name)
      if getattr(method, shop_floor_handler.RPC_METHOD_ATTRIBUTE, False):
        self.dispatcher.register_function(method)

  def _XMLRPCCall(self, session):
    """Dispatches request data body.

    Args:
      session: WSGISession object.
    """
    mediator = SessionMediator(session, self.dispatcher)
    request = ''
    response = ''
    try:
      request = self._ReadRequest(session)
      response = mediator.MarshaledDispatch(request)
    except:  # pylint: disable=W0702
      return session.ServerError500()
    else:
      # Sending valid XML RPC response data
      return session.Respond(response, umpire_wsgi.WSGISession.TEXT_XML)
    finally:
      self._LogRPCCall(session, request, response)

  def _ReadRequest(self, session):
    """Reads request from session.

    Args:
      session: WSGISession object.

    Returns:
      request data.
    """
    # Read body in chunks to avoid straining (python bug #792570)
    size_remaining = session.content_length
    chunks = []
    while size_remaining > 0:
      chunk_size = min(self._MAX_CHUNK_SIZE, size_remaining)
      buf = session.Read(chunk_size)
      if not buf:
        break
      chunks.append(buf)
      size_remaining -= len(buf)
    return ''.join(chunks)

  def _LogRPCCall(self, session, request, response):
    """Logs RPC info.

    Logs RPC request IP, method, process duration, in/out size and error
    message if available.
    """
    LOG_MESSAGE = ('{remote_address} {method} [{duration:.3f} s, '
                   '{in_size:d} B in, {out_size:d} B out]{error}')
    error_message = session[SessionMediator.XMLRPC_EXCEPTION]
    error_message = ': %s' % error_message if error_message else ''
    duration = time.time() - session.time
    # pylint: disable=W1202
    logging.info(LOG_MESSAGE.format(
        remote_address=session.remote_address,
        method=session[SessionMediator.XMLRPC_METHOD],
        duration=duration,
        in_size=len(request),
        out_size=len(response),
        error=error_message))
