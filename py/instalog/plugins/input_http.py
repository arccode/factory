#!/usr/bin/python2
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input HTTP plugin.

Receives events from output HTTP plugin or HTTP requests.
Can easily send one event by curl:
$ curl -i -X POST -F 'event={Payload}' TARGET_HOSTNAME:TARGET_PORT
$ curl -i -X POST \
       -F 'event={"name": "value", ...}' \
       -F 'att_0=@/path/to/attachment_name' \
       TARGET_HOSTNAME:TARGET_PORT

Also can send multiple events by adding header through curl:
$ curl -i -X POST \
       -F 'event={Payload}' \
       -F 'event=[{Payload}, {Attachments}]' \
       -F 'event=[{"name": "value"}, {"0": "att_0"}]' \
       -F 'att_0=@/path/to/attachment_name' \
       -H 'Multi-Event: True' \
       TARGET_HOSTNAME:TARGET_PORT
(See datatypes.py Event.Deserialize for details of event format.)
"""

from __future__ import print_function

import BaseHTTPServer
import cgi
import logging
import shutil
import tempfile
import threading

try:
  import cStringIO as StringIO
except ImportError:
  import StringIO

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog.external import gnupg
from instalog import log_utils
from instalog import plugin_base
from instalog.plugins import http_common
from instalog.utils.arg_utils import Arg
from instalog.utils import file_utils
from instalog.utils import net_utils
from instalog.utils import time_utils


_HTTP_SUMMARY_INTERVAL = 60  # 60sec
_DEFAULT_HOSTNAME = '0.0.0.0'


class InstalogFieldStorage(cgi.FieldStorage):
  """A special version of FieldStorage dedicated for Instalog plugins.

  This class always reads 'events' into memory, and attachments into disk.

  Note curreny implementation is using few internal functions and variables from
  Python 2.7 cgi module, and may not work for different Python versions.
  """

  def __init__(self, tmp_dir, *args, **kargs):
    self.tmp_dir = tmp_dir
    self.FieldStorageClass = lambda *args, **kargs: InstalogFieldStorage(
        self.tmp_dir, *args, **kargs)
    cgi.FieldStorage.__init__(self, *args, **kargs)

  def read_lines(self):
    # Never use fast cache (__file) and always use make_file.
    # pylint: disable=attribute-defined-outside-init
    self._FieldStorage__file = None
    self.file = self.make_file()
    if self.outerboundary:
      self.read_lines_to_outerboundary()
    else:
      self.read_lines_to_eof()

  def make_file(self, binary=None):
    """Always use memory.

    When the content is larger than 1k, FieldStorage will call make_file to
    create a real file on disk for. For Instalog, we want to always use
    in-memory buffer. Note there will still be one copy in __write, but
    there won't be system calls for creating or deleting files (and no fd used).
    """
    del binary  # Unused.
    if not self.name or self.name == 'event':
      return StringIO.StringIO()

    # Save attachments.
    return tempfile.NamedTemporaryFile(
        'wb', prefix=self.name + '_', dir=self.tmp_dir, delete=False)


class HTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler, log_utils.LoggerMixin):
  """Processes HTTP request and responses."""

  def __init__(self, request, client_address, server):
    self.logger = server.context['logger']
    self._plugin_api = server.context['plugin_api']
    self._max_bytes = server.context['max_bytes']
    self._gpg = server.context['gpg']
    self._check_format = server.context['check_format']
    self._log_summary = server.context['log_summary']
    self._enable_multi_event = False
    BaseHTTPServer.BaseHTTPRequestHandler.__init__(self, request,
                                                   client_address, server)

  def _SendResponse(self, status_code, resp_reason):
    """Responds status code, reason and Maximum-Bytes header to client."""
    self.send_response(status_code, resp_reason)
    self.send_header('Maximum-Bytes', self._max_bytes)
    self.end_headers()

  def do_GET(self):
    """Checks the server is online or not."""
    self._SendResponse(200, 'OK')
    self.wfile.write('Instalog input HTTP plugin is online now.\n')
    self.wfile.close()

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
    if self.headers.getheader('Multi-Event', 'False') == 'True':
      self._enable_multi_event = True
    # Create the temporary directory for attachments.
    with file_utils.TempDirectory(prefix='input_http_') as tmp_dir:
      self.debug('Temporary directory for attachments: %s', tmp_dir)
      self.debug('Received POST request from %s:%d',
                 self.client_address[0], self.client_address[1])
      status_code, resp_reason = self._ProcessRequest(tmp_dir,
                                                      int(content_length))
      self._SendResponse(status_code, resp_reason)

  def _ProcessRequest(self, tmp_dir, content_length):
    """Checks the request and processes it.

    Returns:
      A tuple with (HTTP status code, the reason of the response)
    """
    events = []
    try:
      form = InstalogFieldStorage(
          tmp_dir=tmp_dir,
          fp=self.rfile,
          headers=self.headers,
          environ={'REQUEST_METHOD': 'POST'}
      )
      remaining_att = set(form.keys())
      event_list = form.getlist('event')
      remaining_att.remove('event')
      # To avoid confusion, we only allow processing one event per request.
      if not self._enable_multi_event and len(event_list) > 1:
        raise ValueError('One request should not exceed one event')

      for serialize_event in event_list:
        if self._gpg:
          serialize_event = self._DecryptData(serialize_event)
        event = datatypes.Event.Deserialize(serialize_event)

        if not self._enable_multi_event:
          if len(event.attachments) != 0:
            raise ValueError('Please follow the format: event={Payload}')
          requests_keys = form.keys()
          for key in requests_keys:
            if key != 'event':
              event.attachments[key] = key

        for att_id, att_key in event.attachments.iteritems():
          if att_key not in form or isinstance(form[att_key], list):
            raise ValueError('Attachment(%s) should have exactly one in the '
                             'request' % att_key)
          if att_key not in remaining_att:
            raise ValueError('Attachment(%s) should be used by one event' %
                             att_key)
          remaining_att.remove(att_key)
          event.attachments[att_id] = form[att_key].file.name
          if self._gpg:
            self._DecryptFile(event.attachments[att_id], tmp_dir)

        self._check_format(event)
        events.append(event)
      del form  # Free memory earlier.
      if remaining_att:
        raise ValueError('Additional fields: %s' % list(remaining_att))
    except Exception as e:
      self.warning('Bad request with exception: %s', repr(e))
      return 400, 'Bad request: ' + repr(e)
    if len(events) == 0:
      return 200, 'OK'
    elif self._plugin_api.Emit(events):
      self._log_summary(len(events), content_length)
      return 200, 'OK'
    else:
      self.warning('Emit failed')
      return 400, 'Bad request: Emit failed'

  def _CheckDecryptedData(self, decrypted_data):
    """Checks if the data is decrypted and verified."""
    if not decrypted_data.ok:
      raise Exception('Failed to decrypt! Log: %s' % decrypted_data.stderr)
    if (decrypted_data.trust_level is None or
        decrypted_data.trust_level < decrypted_data.TRUST_FULLY):
      raise Exception('Failed to verify!')

  def _DecryptData(self, data):
    """Decrypts and verifies the data."""
    decrypted_data = self._gpg.decrypt(data)
    self._CheckDecryptedData(decrypted_data)
    return decrypted_data.data

  def _DecryptFile(self, file_path, target_dir):
    """Decrypts and verifies the file."""
    with file_utils.UnopenedTemporaryFile(prefix='decrypt_',
                                          dir=target_dir) as tmp_path:
      with open(file_path, 'r') as encrypted_file:
        decrypted_data = self._gpg.decrypt_file(
            encrypted_file, output=tmp_path)
        self._CheckDecryptedData(decrypted_data)
      shutil.move(tmp_path, file_path)

  def log_request(self, code='-', size='-'):
    """Overrides log_request to Instalog format."""
    self.debug('Send response: %s %d', self.requestline, code)

  def log_message(self, format, *args):  # pylint: disable=W0622
    """Overrides log_message to Instalog format."""
    self.warning('%s - %s', self.client_address[0], format % args)


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
    self.server_close()
    net_utils.ShutdownTCPServer(self)
    self._handle_request_thread.join()
    # Wait the process request threads not yet finished.
    threads_copy = self._threads.copy()
    for t in threads_copy:
      t.join()


class InputHTTP(plugin_base.InputPlugin):

  ARGS = [
      Arg('hostname', (str, unicode),
          'Hostname that server should bind to.',
          optional=True, default=_DEFAULT_HOSTNAME),
      Arg('port', int,
          'Port that server should bind to.',
          optional=True, default=http_common.DEFAULT_PORT),
      Arg('max_bytes', int,
          'Maximum size of the request in bytes.',
          optional=True, default=http_common.DEFAULT_MAX_BYTES),
      Arg('enable_gnupg', bool,
          'Enable to use GnuPG.',
          optional=True, default=False),
      Arg('gnupg_home', (str, unicode),
          'The home directory of GnuPG.',
          optional=True, default=None),
  ]

  def __init__(self, *args, **kwargs):
    self._http_server = None
    self._summary_lock = None
    self._last_summary_time = None
    self._request_count = 0
    self._event_count = 0
    self._byte_count = 0
    super(InputHTTP, self).__init__(*args, **kwargs)

  def SetUp(self):
    """Sets up the plugin."""
    logging.getLogger('gnupg').setLevel(logging.WARNING)
    gpg = None
    if self.args.enable_gnupg:
      self.info('Enable GnuPG to decrypt and verify the data')
      http_common.CheckGnuPG()
      # pylint: disable=unexpected-keyword-arg
      gpg = gnupg.GPG(homedir=self.args.gnupg_home)
      self.info('GnuPG home directory: %s', gpg.homedir)
      if len(gpg.list_keys(True)) < 1:
        raise Exception('Need at least one GnuPG secret key in gnupghome')

    self._http_server = ThreadedHTTPServer(
        self.logger, (self.args.hostname, self.args.port), HTTPHandler)
    self._http_server.context = {
        'max_bytes': self.args.max_bytes,
        'gpg': gpg,
        'logger': self.logger,
        'plugin_api': self,
        'check_format': self._CheckFormat,
        'log_summary': self._LogSummary}
    self._http_server.StartServer()
    self.info('http now listening on %s:%d...',
              self.args.hostname, self.args.port)

    self._summary_lock = threading.Lock()
    self._last_summary_time = time_utils.MonotonicTime()

  def TearDown(self):
    """Tears down the plugin."""
    self._http_server.StopServer()
    self.info('Shutdown complete')

  def _CheckFormat(self, event):
    """Checks the event is following the format or not.

    Raises:
      Exception: the event is not conform to the format.
    """
    pass

  def _LogSummary(self, event_num, size):
    """Logs summary after at least a period of time."""
    with self._summary_lock:
      self._request_count += 1
      self._event_count += event_num
      self._byte_count += size
      time_now = time_utils.MonotonicTime()

      if time_now - self._last_summary_time >= _HTTP_SUMMARY_INTERVAL:
        self.info('Over last %.1f sec, received %d requests, total %d events '
                  '(%.2f kB)', time_now - self._last_summary_time,
                  self._request_count, self._event_count,
                  self._byte_count / 1024.0)
        self._last_summary_time = time_now
        self._request_count = 0
        self._event_count = 0
        self._byte_count = 0


if __name__ == '__main__':
  plugin_base.main()
