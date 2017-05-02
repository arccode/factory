#!/usr/bin/python2
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input HTTP plugin.

Receives events from some HTTP requests.
Can easily send events by curl:
$ curl -i -X POST \
       -F 'event={Payload}' \
       -F 'event=[{Payload}, {Attachments}]' \
       -F 'event=[{"name": "value"}, {"0": "att_0"}]' \
       -F 'att_0=@/path/to/attachment_name' \
       TARGET_HOSTNAME:TARGET_PORT
(See datatypes.py Event.Deserialize for details of event format.)
"""

from __future__ import print_function

import BaseHTTPServer
import cgi
import os
import shutil
import tempfile
import threading

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import log_utils
from instalog import plugin_base
from instalog.utils.arg_utils import Arg
from instalog.utils import net_utils


_DEFAULT_MAX_BYTES = 2 * 1024 * 1024 * 1024  # 2gb
_DEFAULT_HOSTNAME = '0.0.0.0'
_DEFAULT_PORT = 8899


class HTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler, log_utils.LoggerMixin):
  """Processes HTTP request and responses."""

  def __init__(self, request, client_address, server):
    self.logger = server.context['logger']
    self._plugin_api = server.context['plugin_api']
    self._max_bytes = server.context['max_bytes']
    self._tmp_dir = None
    BaseHTTPServer.BaseHTTPRequestHandler.__init__(self, request,
                                                   client_address, server)

  def _SendResponse(self, status_code, resp_reason):
    """Responds status code, reason and Maximum-Bytes header to client."""
    self.send_response(status_code, resp_reason)
    self.send_header('Maximum-Bytes', self._max_bytes)
    self.end_headers()

  def do_POST(self):
    """Processes when receiving POST request."""
    content_type = self.headers.getheader('Content-Type', '')
    content_length = self.headers.getheader('Content-Length', None)
    # Need to reject other Content-Type, because Content-Type =
    # 'application/x-www-form-urlencoded' may use about 81 times of data size
    # of memory.
    if not content_type.startswith('multipart/form-data'):
      self._SendResponse(406, 'Not Acceptable: Only accept Content-Type = '
                              'multipart/form-data, please use output HTTP '
                              'plugin or curl command')
      return
    if not content_length:
      self._SendResponse(411, 'Length Required: Need header Content-Length')
      return
    # Content-Length may be wrong, and may cause some security issue.
    if int(content_length) > self._max_bytes:
      self._SendResponse(413, 'Request Entity Too Large: The request is bigger '
                              'than %d bytes' % self._max_bytes)
      return
    # Create the temporary directory for attachments.
    self._tmp_dir = tempfile.mkdtemp(prefix='input_http_')
    self.debug('Temporary directory for attachments: %s', self._tmp_dir)
    self.info('Received POST request from %s:%d',
              self.client_address[0], self.client_address[1])
    status_code, resp_reason = self._ProcessRequest()
    self._SendResponse(status_code, resp_reason)

    # Remove the temporary directory.
    self.debug('Removing temporary directory %s...', self._tmp_dir)
    shutil.rmtree(self._tmp_dir)

  def _ProcessRequest(self):
    """Checks the request and processes it.

    Returns:
      A tuple with (HTTP status code, the reason of the response)
    """
    events = []
    try:
      form = cgi.FieldStorage(
          fp=self.rfile,
          headers=self.headers,
          environ={'REQUEST_METHOD': 'POST'}
      )
      event_list = form.getlist('event')
      for serialize_event in event_list:
        event = datatypes.Event.Deserialize(serialize_event)
        for att_id, att_path in event.attachments.iteritems():
          if att_path not in form or isinstance(form[att_path], list):
            raise Exception('att_path should have exactly one in the request')
          event.attachments[att_id] = self._RecvAttachment(form[att_path])
        events.append(event)
    except Exception as e:
      self.warning('Bad request with error: %s', repr(e))
      return 400, 'Bad request: ' + repr(e)
    if len(events) == 0:
      return 200, 'OK'
    elif self._plugin_api.Emit(events):
      return 200, 'OK'
    else:
      self.warning('Emit failed')
      return 400, 'Bad request: Emit failed'

  def _RecvAttachment(self, data):
    """Receives attachment and saves it as tmp_path in _tmp_dir."""
    fd, tmp_path = tempfile.mkstemp(prefix=data.name + '_', dir=self._tmp_dir)
    with os.fdopen(fd, 'w') as f:
      if data.file:
        shutil.copyfileobj(data.file, f)
      # cgi.MiniFieldStorage does not have attribute 'file', since it stores
      # the binary data in-memory.
      else:
        f.write(data.value)
    self.debug('Temporary save the attachment to: %s', tmp_path)
    return tmp_path

  def log_request(self, code='-', size='-'):
    """Override log_request to Instalog format."""
    self.info('Send response: %s %d', self.requestline, code)

  def log_message(self, format, *args):  # pylint: disable=W0622
    """Override log_message to Instalog format."""
    self.error("%s - %s", self.client_address[0], format % args)


class ThreadedHTTPServer(BaseHTTPServer.HTTPServer, log_utils.LoggerMixin):
  """HTTP server that handles requests in separate threads."""

  def __init__(self, logger, *args, **kwargs):
    self.logger = logger
    self.context = None
    self._threads = set()
    self._handle_request_thread = threading.Thread(target=self.serve_forever)
    BaseHTTPServer.HTTPServer.__init__(self, *args, **kwargs)

  def _ProcessRequestThread(self, request, client_address):
    """Processes the request and handles exceptions."""
    try:
      self.finish_request(request, client_address)
      self.shutdown_request(request)
    except Exception:
      self.handle_error(request, client_address)
      self.shutdown_request(request)
    finally:
      self._threads.remove(threading.currentThread())

  def process_request(self, request, client_address):
    """Starts a new thread to process the request."""
    t = threading.Thread(target=self._ProcessRequestThread,
                         args=(request, client_address))
    self._threads.add(t)
    t.daemon = False
    t.start()

  def StartServer(self):
    """Starts the HTTP server."""
    self._handle_request_thread.start()

  def StopServer(self):
    """Stops the HTTP server."""
    net_utils.ShutdownTCPServer(self)
    self._handle_request_thread.join()
    # Wait the process request threads not yet finished.
    threads_copy = self._threads.copy()
    for t in threads_copy:
      t.join()


class InputHTTP(plugin_base.InputPlugin):

  ARGS = [
      Arg('hostname', (str, unicode), 'Hostname that server should bind to.',
          optional=True, default=_DEFAULT_HOSTNAME),
      Arg('port', int, 'Port that server should bind to.',
          optional=True, default=_DEFAULT_PORT),
      Arg('max_bytes', int, 'Maximum size of the request in bytes.',
          optional=True, default=_DEFAULT_MAX_BYTES)
  ]

  def __init__(self, *args, **kwargs):
    self._http_server = None
    super(InputHTTP, self).__init__(*args, **kwargs)

  def SetUp(self):
    """Sets up the plugin."""
    self._http_server = ThreadedHTTPServer(
        self.logger, (self.args.hostname, self.args.port), HTTPHandler)
    self._http_server.context = {
        'max_bytes': self.args.max_bytes,
        'logger': self.logger,
        'plugin_api': self}
    self._http_server.StartServer()
    self.info('http now listening on %s:%d...',
              self.args.hostname, self.args.port)

  def TearDown(self):
    """Tears down the plugin."""
    self._http_server.StopServer()
    self.info('Shutdown complete')


if __name__ == '__main__':
  plugin_base.main()
