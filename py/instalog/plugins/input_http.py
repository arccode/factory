#!/usr/bin/env python3
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input HTTP plugin.

Receives events from output HTTP plugin or HTTP requests.
Can easily send one event by curl:
$ curl -i -X POST --form-string 'event={Payload}' TARGET_HOSTNAME:TARGET_PORT
$ curl -i -X POST \
       --form-string 'event={"name": "value", ...}' \
       --form 'att_0=@/path/to/attachment_name' \
       TARGET_HOSTNAME:TARGET_PORT

Also can send multiple events by adding header through curl:
$ curl -i -X POST \
       --form-string 'event={Payload}' \
       --form-string 'event=[{Payload}, {Attachments}]' \
       --form-string 'event=[{"name": "value"}, {"0": "att_0"}]' \
       --form 'att_0=@/path/to/attachment_name' \
       -H 'Multi-Event: True' \
       TARGET_HOSTNAME:TARGET_PORT
(See datatypes.py Event.Deserialize for details of event format.)
"""

import cgi
import http.server
from io import StringIO
from io import BytesIO
import logging
import shutil
import tempfile
import threading
import time

from cros.factory.instalog import datatypes
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_base
from cros.factory.instalog.plugins import http_common
from cros.factory.instalog.utils.arg_utils import Arg
from cros.factory.instalog.utils import file_utils
from cros.factory.instalog.utils import net_utils
from cros.factory.instalog.external import gnupg


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

  def make_file(self):
    """Always use memory.

    When the content is larger than 1k, FieldStorage will call make_file to
    create a real file on disk for. For Instalog, we want to always use
    in-memory buffer. Note there will still be one copy in __write, but
    there won't be system calls for creating or deleting files (and no fd used).
    """
    if not self.name or self.name == 'event':
      if self._binary_file:
        return BytesIO()
      return StringIO()

    # Save attachments.
    mode = 'w'
    if self._binary_file:
      mode = 'wb'
    return tempfile.NamedTemporaryFile(
        mode, prefix=self.name + '_', dir=self.tmp_dir, delete=False)


class HTTPHandler(http.server.BaseHTTPRequestHandler, log_utils.LoggerMixin):
  """Processes HTTP request and responses."""

  def __init__(self, request, client_address, server):
    self.logger = logging.getLogger(server.context['logger_name'])
    self._plugin_api = server.context['plugin_api']
    self._max_bytes = server.context['max_bytes']
    self._gpg = server.context['gpg']
    self._check_format = server.context['check_format']
    self._enable_multi_event = False
    self.content_length = 0
    self.client_node_id = 'NoNodeID'
    http.server.BaseHTTPRequestHandler.__init__(self, request, client_address,
                                                server)

  def _SendResponse(self, status_code, resp_reason):
    """Responds status code, reason and Maximum-Bytes header to client."""
    self.send_response(status_code, resp_reason)
    self.send_header('Maximum-Bytes', self._max_bytes)
    self.end_headers()

  def do_GET(self):
    """Checks the server is online or not."""
    self._SendResponse(200, 'OK')
    self.wfile.write(b'Instalog input HTTP plugin is online now.\n')
    self.wfile.close()

  def do_POST(self):
    """Processes when receiving POST request."""
    content_type = self.headers.get('Content-Type', '')
    self.content_length = self.headers.get('Content-Length', None)
    self.client_node_id = self.headers.get('Node-ID', 'NoNodeID')
    # Need to reject other Content-Type, because Content-Type =
    # 'application/x-www-form-urlencoded' may use about 81 times of data size
    # of memory.
    if not content_type.startswith('multipart/form-data'):
      self._SendResponse(406, 'Not Acceptable: Only accept Content-Type = '
                              'multipart/form-data, please use output HTTP '
                              'plugin or curl command')
      return
    if not self.content_length:
      self._SendResponse(411, 'Length Required: Need header Content-Length')
      return
    # Content-Length may be wrong, and may cause some security issue.
    if int(self.content_length) > self._max_bytes:
      self._SendResponse(413, 'Request Entity Too Large: The request is bigger '
                              'than %d bytes' % self._max_bytes)
      return
    if self.headers.get('Multi-Event', 'False') == 'True':
      self._enable_multi_event = True
    # Create the temporary directory for attachments.
    with file_utils.TempDirectory(prefix='input_http_') as tmp_dir:
      self.debug('Temporary directory for attachments: %s', tmp_dir)
      status_code, resp_reason = self._ProcessRequest(tmp_dir)
      self._SendResponse(status_code, resp_reason)

  def _ProcessRequest(self, tmp_dir):
    """Checks the request and processes it.

    Returns:
      A tuple with (HTTP status code, the reason of the response)
    """
    start_time = time.time()

    events = []
    ignore_count = 0
    try:
      form = InstalogFieldStorage(
          tmp_dir=tmp_dir,
          fp=self.rfile,
          headers=self.headers,
          environ={'REQUEST_METHOD': 'POST'}
      )

      receive_time = time.time() - start_time
      start_time = time.time()

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
          if event.attachments:
            raise ValueError('Please follow the format: event={Payload}')
          requests_keys = form.keys()
          for key in requests_keys:
            if key != 'event':
              event.attachments[key] = key

        for att_id, att_key in event.attachments.items():
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

        if self._check_format(event, self.client_node_id):
          events.append(event)
        else:
          ignore_count += 1
      del form  # Free memory earlier.
      if remaining_att:
        raise ValueError('Additional fields: %s' % list(remaining_att))
    except Exception as e:
      self.exception('Bad request with exception: %s', repr(e))
      return 400, 'Bad request: ' + repr(e)

    process_time = time.time() - start_time
    start_time = time.time()

    if not events:
      return 200, 'OK'
    if self._plugin_api.Emit(events):

      emit_time = time.time() - start_time

      self.info('Received %d (ignored %d) events (%s bytes) in %.1f+%.1f+%.1f '
                'sec from node "%s"', len(events), ignore_count,
                self.content_length, receive_time, process_time, emit_time,
                self.client_node_id)
      return 200, 'OK'
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
    if isinstance(data, str):
      data = data.encode('utf-8')
    decrypted_data = self._gpg.decrypt(data, always_trust=False)
    self._CheckDecryptedData(decrypted_data)
    return decrypted_data.data

  def _DecryptFile(self, file_path, target_dir):
    """Decrypts and verifies the file."""
    with file_utils.UnopenedTemporaryFile(prefix='decrypt_',
                                          dir=target_dir) as tmp_path:
      with open(file_path, 'rb') as encrypted_file:
        decrypted_data = self._gpg.decrypt_file(
            encrypted_file, output=tmp_path, always_trust=False)
        self._CheckDecryptedData(decrypted_data)
      shutil.move(tmp_path, file_path)

  def log_request(self, code='-', size='-'):
    """Overrides log_request to Instalog format."""
    del size  # Unused.
    self.debug('Send response: %s %d', self.requestline, code)

  def log_message(self, format, *args):  # pylint: disable=redefined-builtin
    """Overrides log_message to Instalog format."""
    self.warning('%s - %s - %s',
                 self.client_node_id, self.client_address[0], format % args)


class ThreadedHTTPServer(http.server.HTTPServer, log_utils.LoggerMixin):
  """HTTP server that handles requests in separate threads."""

  def __init__(self, logger_name, *args, **kwargs):
    self.logger = logging.getLogger(logger_name)
    self.context = None
    self._threads = set()
    self._handle_request_thread = threading.Thread(target=self.serve_forever)
    http.server.HTTPServer.__init__(self, *args, **kwargs)

  def get_request(self):
    """Overrides get_request to set socket timeout"""
    socket, address = self.socket.accept()
    socket.settimeout(http_common.HTTP_TIMEOUT)
    return (socket, address)

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
    self.server_close()
    self._handle_request_thread.join()
    # Wait the process request threads not yet finished.
    threads_copy = self._threads.copy()
    for t in threads_copy:
      t.join()


class InputHTTP(plugin_base.InputPlugin):

  ARGS = [
      Arg('hostname', str,
          'Hostname that server should bind to.',
          default=_DEFAULT_HOSTNAME),
      Arg('port', int,
          'Port that server should bind to.',
          default=http_common.DEFAULT_PORT),
      Arg('max_bytes', int,
          'Maximum size of the request in bytes.',
          default=http_common.DEFAULT_MAX_BYTES),
      Arg('enable_gnupg', bool,
          'Enable to use GnuPG.',
          default=False),
      Arg('gnupg_home', str,
          'The home directory of GnuPG.',
          default=None),
  ]

  def __init__(self, *args, **kwargs):
    self._http_server = None
    super(InputHTTP, self).__init__(*args, **kwargs)

  def SetUp(self):
    """Sets up the plugin."""
    logging.getLogger('gnupg').setLevel(logging.WARNING)
    gpg = None
    if self.args.enable_gnupg:
      self.info('Enable GnuPG to decrypt and verify the data')
      http_common.CheckGnuPG()
      gpg = gnupg.GPG(gnupghome=self.args.gnupg_home)
      self.info('GnuPG home directory: %s', gpg.gnupghome)
      if len(gpg.list_keys(True)) < 1:
        raise Exception('Need at least one GnuPG secret key in gnupghome')

    self._http_server = ThreadedHTTPServer(
        self.logger.name, (self.args.hostname, self.args.port), HTTPHandler)
    self._http_server.context = {
        'max_bytes': self.args.max_bytes,
        'gpg': gpg,
        'logger_name': self.logger.name,
        'plugin_api': self,
        'check_format': self._CheckFormat}
    self._http_server.StartServer()
    self.info('http now listening on %s:%d...',
              self.args.hostname, self.args.port)

  def TearDown(self):
    """Tears down the plugin."""
    self._http_server.StopServer()
    self.info('Shutdown complete')

  def _CheckFormat(self, event, client_node_id):
    """Checks the event is following the format or not.

    Raises:
      Exception: the event is not conform to the format.
    """
    del event, client_node_id
    return True


if __name__ == '__main__':
  plugin_base.main()
