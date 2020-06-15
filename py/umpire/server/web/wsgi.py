# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""WSGI session class.

This class provides shortcuts to HTTP request and response.
"""

import logging
import time

from twisted.web import http

from cros.factory.utils import type_utils


class WSGISession(type_utils.AttrDict):
  """WSGI session class.

  This class converts WSGI environ to an AttrDict.

  Properties:
    start_response: WSGI response object.

  WSGI properties:
    wsgi_version: WSGI version (major, minor) tuple.
    wsgi_url_scheme: the scheme portion of URL, 'http' or 'https'.
    wsgi_input: input stream file-like object.
    wsgi_error: error logging file-like output object.
    REQUEST_METHOD: 'GET' or 'POST'.
    PATH_INFO: path portion of URL.
    QUERY_STRING: the portion of URL follows '?'.
    HTTP_* : client supplied HTTP request headers.
  """

  TEXT_PLAIN = 'text/plain'
  TEXT_XML = 'text/xml'

  def __init__(self, environ, start_response):
    """Constructs WSGISession using WSGI environ and start_response.

    The ctor converts WSGI environ into AttrDict. And copies values in 'wsgi.*'
    to 'wsgi_*' attributes.

    Args:
      environ: WSGI environ dictionary.
      start_response: WSGI start_response object.
    """
    super(WSGISession, self).__init__(environ)
    for key, value in environ.items():
      if key.startswith('wsgi.'):
        key = 'wsgi_' + key[5:]
      self[key] = value
    self.start_response = start_response
    self.time = time.time()

  @property
  def remote_address(self):
    """Gets HTTP remote address.

    This function returns environ["REMOTE_ADDR"] if the connection is not
    proxied. When connection was went through proxies. It returns the closest
    remote address in proxy chain.

    Returns:
      remote address.
    """
    try:
      return self.HTTP_X_FORWARDED_FOR.split(',')[-1].strip()
    except Exception:
      return self.REMOTE_ADDR

  @property
  def content_length(self):
    """Gets numeric request content length."""
    return int(self.CONTENT_LENGTH)

  def Read(self, size=None):
    """Reads HTTP request body.

    Args:
      size: read bytes. If not specified or size == 0, returns whole
      request content.
    """
    if size:
      return self.wsgi_input.read(size)
    return self.wsgi_input.read(self.content_length)

  def GetMessage(self, code):
    """Gets HTTP response code and message.

    Returns:
      (response code, message) tuple.
    """
    return '%d %s' % (code, http.RESPONSES.get(code, 'Unknown Status'))

  def Respond(self, data=b'', content_type=TEXT_PLAIN, code=http.OK):
    """Sends response header then returns body.

    Args:
      data: the response body.
      content_type: IANA media type of data.
      code: HTTP response code.

    Returns:
      WSGI return body list.
    """
    if isinstance(data, str):
      data = data.encode('utf-8')

    code_message = self.GetMessage(code)
    if content_type is None:
      content_type = self.TEXT_PLAIN

    headers = [('Content-Type', content_type)]
    if data:
      headers.append(('Content-Length', str(len(data))))
    self.start_response(code_message, headers)
    return [data]

  def BadRequest400(self):
    return self.Respond(code=http.BAD_REQUEST)

  def ServerError500(self):
    return self.Respond(code=http.INTERNAL_SERVER_ERROR)

  def MethodNotAllowed405(self):
    return self.Respond(code=http.NOT_ALLOWED)

  def Gone410(self):
    return self.Respond(code=http.GONE)


class WebAppDispatcher(dict):
  """Web application path dispatcher.

  The dispatcher is a WSGI web application that dispatches HTTP requests
  according to environ['PATH_INFO'].
  """

  def __call__(self, environ, start_response):
    session = WSGISession(environ, start_response)
    try:
      if session.PATH_INFO in self:
        return self[session.PATH_INFO](environ, start_response)
      logging.error('request path does not exist: %s', session.PATH_INFO)
      logging.error('  : keys = %s', list(self))
      return session.MethodNotAllowed405()
    except Exception:
      logging.exception('web app exception')
      return session.ServerError500()


class WebApp:
  """Web application class."""

  def __call__(self, environ, start_response):
    return self.Handle(WSGISession(environ, start_response))

  def Handle(self, session):
    raise NotImplementedError
