#!/usr/bin/env python3
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import cgi
import http.server
import logging
import os
import queue
import shutil
import socketserver
import tempfile
import threading
import unittest

from cros.factory.instalog import datatypes
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_sandbox
from cros.factory.instalog.plugins import output_http
from cros.factory.instalog import testing
from cros.factory.instalog.utils import net_utils


class TestOutputHTTP(unittest.TestCase):

  def _CreatePlugin(self):
    self.core = testing.MockCore()
    self.hostname = 'localhost'
    self.port = net_utils.FindUnusedPort()

    # Create PluginSandbox for output plugin.
    output_config = {
        'hostname': 'localhost',
        'port': self.port,
        'url_path': 'instalog',
        'batch_size': 3,
        'timeout': 10}
    self.output_sandbox = plugin_sandbox.PluginSandbox(
        'output_http', config=output_config, core_api=self.core)

    self.output_sandbox.Start(True)

    # Make reconnection tries faster (default is 60 seconds.)
    # This needs to be set after output_sandbox is started and plugin is loaded.
    # pylint: disable=protected-access
    output_http._FAILED_CONNECTION_INTERVAL = 1

    # Store a BufferEventStream.
    self.stream = self.core.GetStream(0)

  def setUp(self):
    self._CreatePlugin()
    self._tmp_dir = tempfile.mkdtemp(prefix='output_http_unittest_')

  def tearDown(self):
    self.output_sandbox.Stop(True)
    self.core.Close()
    shutil.rmtree(self._tmp_dir)

  def testMultiEvent(self):
    q = queue.Queue()

    class MyHandler(http.server.BaseHTTPRequestHandler):
      def __init__(self, request, client_address, server):
        self._max_bytes = 100 * 1024 * 1024  # 100mb
        http.server.BaseHTTPRequestHandler.__init__(self, request,
                                                    client_address, server)

      def _SendResponse(self, status_code, resp_reason):
        """Responds status code, reason and Maximum-Bytes header to client."""
        self.send_response(status_code, resp_reason)
        self.send_header('Maximum-Bytes', self._max_bytes)
        self.end_headers()

      def do_GET(self):
        """Checks the server is online or not."""
        if self.path != '/instalog':
          self._SendResponse(400, 'Bad url path')
          return

        self._SendResponse(200, 'OK')
        self.wfile.write(b'Instalog input HTTP plugin is online now.\n')
        self.wfile.close()

      def do_POST(self):
        if self.path != '/instalog':
          self._SendResponse(400, 'Bad url path')
          return

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={'REQUEST_METHOD': 'POST'}
        )
        self._SendResponse(200, 'OK')
        q.put(form.getlist('event'))
        q.put(form.getlist('file0_000'))
        q.put(form.getlist('file1_001'))

      def log_request(self, code='-', size='-'):
        """Overrides log_request to Instalog format."""
        del size  # Unused.
        logging.info('Send response: %s %d', self.requestline, code)


    httpd = socketserver.TCPServer(('', self.port), MyHandler)
    T = threading.Thread(target=httpd.serve_forever)
    T.start()
    att_path1 = os.path.join(self._tmp_dir, 'file0')
    att_path2 = os.path.join(self._tmp_dir, 'file1')
    att_data1 = '!' * 10
    att_data2 = '@' * 10
    with open(att_path1, 'w') as f:
      f.write(att_data1)
    with open(att_path2, 'w') as f:
      f.write(att_data2)
    event1 = datatypes.Event({}, {'my_attachment': att_path1})
    event2 = datatypes.Event({'AA': 'BB'}, {'my_attachment': att_path2})
    event3 = datatypes.Event({'CC': 'DD'}, {})
    self.stream.Queue([event1, event2, event3])
    serialized_events = q.get()
    output_event1 = datatypes.Event.Deserialize(serialized_events[0])
    output_event2 = datatypes.Event.Deserialize(serialized_events[1])
    output_event3 = datatypes.Event.Deserialize(serialized_events[2])
    self.assertEqual(output_event1.payload, event1.payload)
    self.assertEqual(output_event1.attachments, {'my_attachment': 'file0_000'})
    self.assertEqual(output_event2.payload, event2.payload)
    self.assertEqual(output_event2.attachments, {'my_attachment': 'file1_001'})
    self.assertEqual(output_event3.payload, event3.payload)
    self.assertEqual(output_event3.attachments, {})
    self.assertEqual(q.get(), [b'!' * 10])
    self.assertEqual(q.get(), [b'@' * 10])
    httpd.shutdown()


if __name__ == '__main__':
  log_utils.InitLogging(log_utils.GetStreamHandler(logging.INFO))
  unittest.main()
