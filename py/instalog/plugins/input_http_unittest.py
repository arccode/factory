#!/usr/bin/env python3
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for input HTTP plugin."""

import http.client
import logging
import os
import queue
import shutil
import tempfile
import threading
import unittest
import urllib.parse

import requests

from cros.factory.instalog import datatypes
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_sandbox
from cros.factory.instalog import testing
from cros.factory.instalog.utils import file_utils
from cros.factory.instalog.utils import net_utils
from cros.factory.instalog.utils import process_utils
from cros.factory.instalog.utils import sync_utils


def _TempAvailSpaceMB():
  output = process_utils.CheckOutput(
      ['df', '--output=avail', '--block-size=1M', tempfile.gettempdir()])
  return int(output.splitlines()[1])


class TestInputHTTP(unittest.TestCase):

  def _CreatePlugin(self):
    self.core = testing.MockCore()
    self.hostname = 'localhost'
    self.port = net_utils.FindUnusedPort()
    config = {
        'hostname': 'localhost',
        'port': self.port}
    self.sandbox = plugin_sandbox.PluginSandbox(
        'input_http', config=config, core_api=self.core)
    self.sandbox.Start(True)
    self.plugin = self.sandbox._plugin  # pylint: disable=protected-access

  def setUp(self):
    self._CreatePlugin()
    self._tmp_dir = tempfile.mkdtemp(prefix='input_http_unittest_')

  def tearDown(self):
    if self.sandbox.GetState() != plugin_sandbox.DOWN:
      self.sandbox.Stop(True)
      self.assertTrue(self.core.AllStreamsExpired())
      self.core.Close()
    shutil.rmtree(self._tmp_dir)

  def _GeneratePayload(self, mbytes):
    path = file_utils.CreateTemporaryFile(dir=self._tmp_dir)
    process_utils.Spawn(
        ['truncate', '-s', str(mbytes * 1024 * 1024), path], check_call=True)
    return path

  def _CurlPost(self, *fields):
    curl_args = ['-X', 'POST', '--silent', '--output', '/dev/null',
                 '--write-out', '%{http_code}',
                 '--header', 'Multi-Event: True']
    for field in fields:
      unused_key, unused_sep, value = field.partition('=')
      curl_args.append('--form' if value[0] == '@' else '--form-string')
      curl_args.append(field)
    status_code_str = process_utils.CheckOutput(
        ['curl'] + curl_args + ['localhost:%d' % self.port], ignore_stderr=True)
    return int(status_code_str)

  def _RequestsPost(self, files=None, multi_event=True, timeout=None):
    # To avoid requests use content-type application/x-www-form-urlencoded
    return requests.post(url='http://localhost:' + str(self.port), files=files,
                         headers={'Multi-Event': str(multi_event)},
                         timeout=timeout)

  def testConnect(self):
    r = requests.get(url='http://localhost:' + str(self.port), timeout=2)
    self.assertEqual(200, r.status_code)
    self.assertIn('Maximum-Bytes', r.headers)
    self.assertEqual(0, len(self.core.emit_calls))

  def _ClientConnected(self):
    # pylint: disable=protected-access
    return len(self.plugin._http_server._threads) > 0

  @unittest.skipIf(_TempAvailSpaceMB() < 256, 'Test requires 256mb disk space.')
  def testShutdown(self):
    """Tests that a request thread should terminate before shutting down."""
    event = datatypes.Event({}, {'att_id': 'att'})
    big_att_path = self._GeneratePayload(128)  # 128mb
    # Use a queue to get the request object out of the thread.
    q = queue.Queue()
    def PostBig():
      event_str = datatypes.Event.Serialize(event)
      r = self._CurlPost('event=%s' % event_str, 'att=@%s' % big_att_path)
      q.put(r)
    t = threading.Thread(target=PostBig)
    t.daemon = False
    t.start()
    sync_utils.WaitFor(self._ClientConnected, 10, poll_interval=0.02)
    self.sandbox.Stop(True)
    self.assertTrue(self.core.AllStreamsExpired())
    self.core.Close()
    self.assertEqual(400, q.get())
    t.join()

  def testShutdownServerClose(self):
    self.sandbox.Stop(True)
    self.assertTrue(self.core.AllStreamsExpired())
    self.core.Close()
    with self.assertRaises(requests.ConnectionError):
      self._RequestsPost(timeout=1)

  def testUnsupportedMethod(self):
    r = requests.put('http://localhost:' + str(self.port))
    self.assertEqual(501, r.status_code)
    r = requests.delete('http://localhost:' + str(self.port))
    self.assertEqual(501, r.status_code)
    r = requests.head('http://localhost:' + str(self.port))
    self.assertEqual(501, r.status_code)
    r = requests.options('http://localhost:' + str(self.port))
    self.assertEqual(501, r.status_code)
    r = requests.patch('http://localhost:' + str(self.port))
    self.assertEqual(501, r.status_code)

  def testNoAttachment(self):
    event = datatypes.Event({}, {'att_id': 'att'})
    data = {'event': datatypes.Event.Serialize(event)}
    r = self._RequestsPost(files=data)
    self.assertEqual(400, r.status_code)
    self.assertEqual('Bad request: ValueError(\'Attachment(att) should have '
                     'exactly one in the request\',)', r.reason)
    self.assertEqual(0, len(self.core.emit_calls))

  def testSameNameAttachment(self):
    event = datatypes.Event({}, {'att_id': 'att'})
    att1 = 'THISISATT1'
    att2 = 'THISISATT2'
    data = [('event', datatypes.Event.Serialize(event)),
            ('att', att1),
            ('att', att2)]
    r = self._RequestsPost(files=data)
    self.assertEqual(400, r.status_code)
    self.assertEqual('Bad request: ValueError(\'Attachment(att) should have '
                     'exactly one in the request\',)', r.reason)
    self.assertEqual(0, len(self.core.emit_calls))

  def testUseSameAttachment(self):
    event1 = datatypes.Event({}, {'att_id': 'att'})
    event2 = datatypes.Event({}, {'att_id': 'att'})
    att = 'THISISATT'
    data = [('event', datatypes.Event.Serialize(event1)),
            ('event', datatypes.Event.Serialize(event2)),
            ('att', att)]
    r = self._RequestsPost(files=data)
    self.assertEqual(400, r.status_code)
    self.assertEqual('Bad request: ValueError(\'Attachment(att) should be '
                     'used by one event\',)', r.reason)
    self.assertEqual(0, len(self.core.emit_calls))

  def testAdditionalAttachment(self):
    event = datatypes.Event({}, {'att_id': 'att1'})
    att1 = 'THISISATT1'
    att2 = 'THISISATT2'
    data = [('event', datatypes.Event.Serialize(event)),
            ('att1', att1),
            ('att2', att2)]
    r = self._RequestsPost(files=data)
    self.assertEqual(400, r.status_code)
    self.assertEqual('Bad request: ValueError("Additional fields: '
                     '[\'att2\']",)', r.reason)
    self.assertEqual(0, len(self.core.emit_calls))

  def testInvalidSingleEvent(self):
    """Tests that event.attachment has additional attachment"""
    event = datatypes.Event({'type': 'other', 'AA': 'BB'}, {'att': 'att'})
    att = os.urandom(1024)  # 1kb data
    data = {'event': datatypes.Event.Serialize(event),
            'att': att}
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(400, r.status_code)
    self.assertEqual('Bad request: ValueError(\'Please follow the format: '
                     'event={Payload}\',)', r.reason)

    event = datatypes.Event(
        {'type': 'other', 'AA': 'BB', 'attachments': {'att_key1': {},
                                                      'att_key2': {}}},
        {'att_key2': 'att_key2'})
    att1 = os.urandom(1024)  # 1kb data
    att2 = os.urandom(1024)  # 1kb data
    data = {'event': datatypes.Event.Serialize(event),
            'att_key1': att1,
            'att_key2': att2}
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(400, r.status_code)
    self.assertEqual('Bad request: ValueError(\'Please follow the format: '
                     'event={Payload}\',)', r.reason)

  def testOneEvent(self):
    event = datatypes.Event({'AA': 'BB'}, {'att_id': 'att'})
    att = os.urandom(1024)  # 1kb data
    data = {'event': datatypes.Event.Serialize(event),
            'att': att}
    r = self._RequestsPost(files=data)
    self.assertEqual(200, r.status_code)
    self.assertEqual(1, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[0]))
    self.assertEqual(event.payload, self.core.emit_calls[0][0].payload)
    with open(self.core.emit_calls[0][0].attachments['att_id'], 'rb') as f:
      self.assertEqual(att, f.read())

    event = datatypes.Event({'AA': 'BB'})
    att = os.urandom(1024)  # 1kb data
    data = {'event': datatypes.Event.Serialize(event),
            'att': att}
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(200, r.status_code)
    self.assertEqual(2, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[1]))
    self.assertEqual(event.payload, self.core.emit_calls[1][0].payload)
    with open(self.core.emit_calls[1][0].attachments['att'], 'rb') as f:
      self.assertEqual(att, f.read())

  def testHTTPlibEvent(self):
    client = http.client.HTTPConnection('localhost', self.port, timeout=180)
    event = datatypes.Event({'AA': 'BB'}, {'att_id': 'att'})
    att = os.urandom(1024)  # 1kb data
    params = urllib.parse.urlencode({'event': datatypes.Event.Serialize(event),
                                     'att': att})
    client.request('POST', '/', params)
    self.assertEqual(406, client.getresponse().status)
    self.assertEqual(0, len(self.core.emit_calls))

  def testMultiEvent(self):
    event1 = datatypes.Event({}, {'att_id': 'att1'})
    event2 = datatypes.Event({'CC': 'DD'}, {})
    event3 = datatypes.Event({'EE': 'FF'}, {'att_id': 'att2'})
    att1 = os.urandom(10)
    att2 = os.urandom(10)
    data = [('event', datatypes.Event.Serialize(event1)),
            ('event', datatypes.Event.Serialize(event2)),
            ('event', datatypes.Event.Serialize(event3)),
            ('att1', att1),
            ('att2', att2)]
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(400, r.status_code)
    self.assertEqual('Bad request: ValueError(\'One request should not exceed '
                     'one event\',)', r.reason)
    self.assertEqual(0, len(self.core.emit_calls))

    r = self._RequestsPost(files=data)
    self.assertEqual(200, r.status_code)
    self.assertEqual(1, len(self.core.emit_calls))
    self.assertEqual(3, len(self.core.emit_calls[0]))
    self.assertEqual(event1.payload, self.core.emit_calls[0][0].payload)
    self.assertEqual(event2.payload, self.core.emit_calls[0][1].payload)
    self.assertEqual(event3.payload, self.core.emit_calls[0][2].payload)
    with open(self.core.emit_calls[0][0].attachments['att_id'], 'rb') as f:
      self.assertEqual(att1, f.read())
    with open(self.core.emit_calls[0][2].attachments['att_id'], 'rb') as f:
      self.assertEqual(att2, f.read())

  @unittest.skipIf(_TempAvailSpaceMB() < 256, 'Test requires 256mb disk space.')
  def testMultithreadedServing(self):
    """Tests that the server has multithreading enabled."""
    event1 = datatypes.Event({'size': 'big'}, {'att_id': 'att'})
    event2 = datatypes.Event({'size': 'small'}, {'att_id': 'att'})
    big_att_path = self._GeneratePayload(128)  # 128mb
    small_data = {'event': datatypes.Event.Serialize(event2),
                  'att': '!' * 1024}  # 1kb

    # Use a queue to get the request object out of the thread.
    q = queue.Queue()
    def PostBig():
      event_str = datatypes.Event.Serialize(event1)
      r = self._CurlPost('event=%s' % event_str, 'att=@%s' % big_att_path)
      q.put(r)
    t = threading.Thread(target=PostBig)
    t.daemon = False
    t.start()

    sync_utils.WaitFor(self._ClientConnected, 10, poll_interval=0.02)
    r = self._RequestsPost(files=small_data, timeout=1)
    t.join()

    self.assertEqual(200, r.status_code)
    self.assertEqual(200, q.get())
    self.assertEqual(2, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[0]))
    self.assertEqual('small', self.core.emit_calls[0][0]['size'])
    self.assertEqual(1, len(self.core.emit_calls[1]))
    self.assertEqual('big', self.core.emit_calls[1][0]['size'])

  def testCurlCommand(self):
    att_path = self._GeneratePayload(1)  # 1mb
    self._CurlPost('event=[{"GG": "HH"}, {"att_id": "att"}]',
                   'att=@%s' % att_path)
    self.assertEqual(1, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[0]))
    self.assertEqual({'GG': 'HH'}, self.core.emit_calls[0][0].payload)
    uploaded_path = self.core.emit_calls[0][0].attachments['att_id']
    self.assertEqual(
        file_utils.ReadFile(uploaded_path), file_utils.ReadFile(att_path))

  @unittest.skip('This test cause a heavy load on disk write, '
                 'and slow down other tests. Please run it manually.')
  def testOneHugeAttachment(self):
    """Tests the ability to transfer one huge attachment."""
    event = datatypes.Event({}, {'att_id': 'att'})
    att_path = self._GeneratePayload(1024)  # 1gb
    event_str = datatypes.Event.Serialize(event)
    r = self._CurlPost('event=%s' % event_str, 'att=@%s' % att_path)
    self.assertEqual(200, r)
    self.assertEqual(1, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[0]))
    uploaded_path = self.core.emit_calls[0][0].attachments['att_id']
    process_utils.Spawn(
        ['cmp', '-s', uploaded_path, att_path], check_call=True)


if __name__ == '__main__':
  log_utils.InitLogging(log_utils.GetStreamHandler(logging.INFO))
  logging.getLogger('requests').setLevel(logging.WARNING)
  unittest.main()
