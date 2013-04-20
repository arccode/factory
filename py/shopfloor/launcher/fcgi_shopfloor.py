# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
This file provides an FastCGI to XMLRPC server interface.

Import this mod and call RunAsFastCGI function to start the server in
FastCGI mode.

Example:
  /path/to/shopfloor_server -f -a 127.0.0.1 -p 8085 \
    -m cros.factory.shopfloor.sample_shopfloor -f
"""


import logging
import multiprocessing
import time
from flup.server.fcgi_fork import WSGIServer
from SimpleXMLRPCServer import SimpleXMLRPCDispatcher

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils


class WSGISession(dict):
  """WSGI session class.

  This class provides shortcuts to access encapsulated WSGI environ dict and
  start_response functor.

  Args:
    environ: WSGI env dictionary.
    start_response: WSGI response functor for sending HTTP response headers.
  """
  TEXT_PLAIN = ('Content-Type', 'text/plain')
  TEXT_XML = ('Content-Type', 'text/xml')

  def __init__(self, environ, start_response, *args, **kwargs):
    super(WSGISession, self).__init__(*args, **kwargs)
    self.environ = environ
    self.time = time.time()
    self.start_response = start_response

  def Method(self):
    """Gets WSGI request method."""
    return self.environ['REQUEST_METHOD']

  def ContentLength(self):
    """Gets numerical WSGI request content length."""
    return int(self.environ['CONTENT_LENGTH'])

  def RemoteAddress(self):
    """Gets HTTP client IP address."""
    try:
      return self.environ['HTTP_X_FORWARDED_FOR'].split(',')[-1].strip()
    except KeyError:
      return self.environ['REMOTE_ADDR']

  def Read(self, size):
    """Reads from WSGI input stream file object."""
    return self.environ['wsgi.input'].read(size)

  def Response(self, content_type, data):
    """Generates WSGI '200 OK' HTTP response.

    Args:
      content_type: IANA media types.
      data: the response body.

    Returns:
      WSGI return body list.
    """
    headers = [('Content-Type', content_type),
               ('Content-Length', str(len(data)))]
    self.start_response('200 OK', headers)
    return [data]

  def BadRequest(self):
    self.start_response('400 Bad Request', [self.TEXT_PLAIN])
    return ['']

  def ServerError(self):
    self.start_response('500 Server Error', [self.TEXT_PLAIN])
    return ['']


class SessionMediator(object):
  """Encapsulator of session and dispatcher.

  This class holds two objects, WSGI session and XMLRPC dispatcher. The RPC
  method and exception are written back to session dictionary.

  Args:
    session: WSGI session object
    dispatcher: XMLRPCDispatcher object
  """
  def __init__(self, session, dispatcher):
    self.session = session
    self.dispatcher = dispatcher
    self.session['xmlrpc_exception'] = None
    self.session['xmlrpc_method'] = ''

  def MarshaledDispatch(self, data):
    return self.dispatcher._marshaled_dispatch(  # pylint: disable=W0212
        data, getattr(self, '_Dispatch', None)) + '\n'

  def _Dispatch(self, method, params):
    try:
      self.session['xmlrpc_method'] = method
      self.session['xmlrpc_params'] = params
      return self.dispatcher._dispatch(method, params)  # pylint: disable=W0212
    except:  # pylint: disable=W0702
      self.session['xmlrpc_exception'] = utils.FormatExceptionOnly()
      raise


class MyXMLRPCApp(object):
  """WSGI to XMLRPC callable.

  XMLRPC WSGI callable app.

  Args:
    instance: An instance of XMLRPC module.

  Callable args:
    environ: WSGI environment dictionary.
    start_response: WSGI response functor for sending HTTP headers.
  """
  _MAX_CHUNK_SIZE = 10 * 1024 * 1024

  def __init__(self, instance):
    """Creates XML RPC dispatcher."""
    self.dispatcher = SimpleXMLRPCDispatcher(allow_none=True, encoding=None)
    self.dispatcher.register_introspection_functions()
    if instance is not None:
      self.RegisterInstance(instance)

  def __call__(self, environ, start_response):
    session = WSGISession(environ, start_response)
    if session.Method() != 'POST':
      return session.BadRequest()
    return self._XMLRPCCall(session)

  def RegisterInstance(self, instance):
    self.dispatcher.register_instance(instance)

  def _XMLRPCCall(self, session):
    """Dispatches request data body."""
    mediator = SessionMediator(session, self.dispatcher)
    response_data = ''
    try:
      # Reading body in chunks to avoid straining (python bug #792570)
      size_remaining = session.ContentLength()
      chunks = []
      while size_remaining > 0:
        chunk_size = min(self._MAX_CHUNK_SIZE, size_remaining)
        buf = session.Read(chunk_size)
        if not buf:
          break
        chunks.append(buf)
        size_remaining -= len(buf)
      data = ''.join(chunks)

      # Dispatching data
      response_data = mediator.MarshaledDispatch(data)
    except:  # pylint: disable=W0702
      return session.ServerError()
    else:
      # Sending valid XML RPC response data
      return session.Response('text/xml', response_data)
    finally:
      error_message = session['xmlrpc_exception']
      error_message = (': %s' % error_message if error_message else '')
      logging.info('%s %s [%3f s, %d B in, %d B out]%s',
                   session.RemoteAddress(),
                   session['xmlrpc_method'],
                   time.time() - session.time,
                   len(data),
                   len(response_data),
                   error_message)


def RunAsFastCGI(address, port, instance):
  """Starts an XML-RPC server in given address:port.

  Args:
    address: IP address to bind
    port: Port for server to listen
    instance: Server instance for incoming XML RPC requests.

  Return:
    Never returns
  """
  application = MyXMLRPCApp(instance=instance)
  bind_address = (address, port)
  cpu_count = multiprocessing.cpu_count()
  fork_args = dict()
  fork_args['minSpare'] = 4
  fork_args['maxSpare'] = cpu_count * 2
  fork_args['maxChildren'] = cpu_count * 100
  fork_args['maxRequests'] = 16
  server = WSGIServer(application, bindAddress=bind_address, **fork_args)
  server.run()


