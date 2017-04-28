#!/usr/bin/python2
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for input HTTP plugin."""

from __future__ import print_function

import httplib
import logging
import os
import Queue
import shutil
import tempfile
import threading
import time
import unittest
import urllib

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import log_utils
from instalog import plugin_sandbox
from instalog import testing
from instalog.utils import net_utils

from instalog.external import requests


class TestInputHTTP(unittest.TestCase):

  def _CreatePlugin(self):
    self.core = testing.MockCore()
    self.hostname = 'localhost'
    self.port = net_utils.GetUnusedPort()
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
    self.sandbox.Stop(True)
    self.assertTrue(self.core.AllStreamsExpired())
    self.core.Close()
    shutil.rmtree(self._tmp_dir)

  def testConnect(self):
    r = requests.post('http://localhost:' + str(self.port), files={'':''})
    self.assertEqual(200, r.status_code)
    self.assertIn('Maximum-Bytes', r.headers)
    self.assertEqual(0, len(self.core.emit_calls))

  def testShutdown(self):
    """Tests that a request thread should terminate before shutting down."""
    event = datatypes.Event({}, {'att_id': 'att'})
    big_data = {'event': datatypes.Event.Serialize(event),
                'att': '!' * 512 * 1024 * 1024}  # 512mb
    # Use a queue to get the request object out of the thread.
    q = Queue.Queue()
    def PostBig():
      try:
        r = requests.post('http://localhost:' + str(self.port), files=big_data)
        q.put(r)
      except Exception as e:
        q.put(e)
    t = threading.Thread(target=PostBig)
    t.daemon = False
    t.start()
    time.sleep(0.2)  # Give the thread a chance to start up.
    self.sandbox.Stop(True)
    self.assertTrue(self.core.AllStreamsExpired())
    self.core.Close()
    self.assertEqual(400, q.get().status_code)
    self._CreatePlugin()  # For tearDown to stop.

  def testUnsupportedMethod(self):
    r = requests.get('http://localhost:' + str(self.port))
    self.assertEqual(501, r.status_code)
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
    r = requests.post('http://localhost:' + str(self.port), files=data)
    self.assertEqual(400, r.status_code)
    self.assertEqual('Bad request: Exception(\'att_path should have exactly '
                     'one in the request\',)', r.reason)
    self.assertEqual(0, len(self.core.emit_calls))

  def testSameNameAttachment(self):
    event = datatypes.Event({}, {'att_id': 'att'})
    att1 = 'THISISATT1'
    att2 = 'THISISATT2'
    data = [('event', datatypes.Event.Serialize(event)),
            ('att', att1),
            ('att', att2)]
    r = requests.post('http://localhost:' + str(self.port), files=data)
    self.assertEqual(400, r.status_code)
    self.assertEqual('Bad request: Exception(\'att_path should have exactly '
                     'one in the request\',)', r.reason)
    self.assertEqual(0, len(self.core.emit_calls))

  def testOneEvent(self):
    event = datatypes.Event({'AA': 'BB'}, {'att_id': 'att'})
    att = os.urandom(1024)  # 1kb data
    data = {'event': datatypes.Event.Serialize(event),
            'att': att}
    r = requests.post('http://localhost:' + str(self.port), files=data)
    self.assertEqual(200, r.status_code)
    self.assertEqual(1, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[0]))
    self.assertEqual(event.payload, self.core.emit_calls[0][0].payload)
    with open(self.core.emit_calls[0][0].attachments['att_id']) as f:
      self.assertEqual(att, f.read())

  def testHTTPlibEvent(self):
    client = httplib.HTTPConnection('localhost', self.port, timeout=180)
    event = datatypes.Event({'AA': 'BB'}, {'att_id': 'att'})
    att = os.urandom(1024)  # 1kb data
    params = urllib.urlencode({'event': datatypes.Event.Serialize(event),
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
    r = requests.post('http://localhost:' + str(self.port), files=data)
    self.assertEqual(200, r.status_code)
    self.assertEqual(1, len(self.core.emit_calls))
    self.assertEqual(3, len(self.core.emit_calls[0]))
    self.assertEqual(event1.payload, self.core.emit_calls[0][0].payload)
    self.assertEqual(event2.payload, self.core.emit_calls[0][1].payload)
    self.assertEqual(event3.payload, self.core.emit_calls[0][2].payload)
    with open(self.core.emit_calls[0][0].attachments['att_id']) as f:
      self.assertEqual(att1, f.read())
    with open(self.core.emit_calls[0][2].attachments['att_id']) as f:
      self.assertEqual(att2, f.read())

  def testMultithreadedServing(self):
    """Tests that the server has multithreading enabled."""
    event1 = datatypes.Event({'size': 'big'}, {'att_id': 'att'})
    event2 = datatypes.Event({'size': 'small'}, {'att_id': 'att'})
    big_data = {'event': datatypes.Event.Serialize(event1),
                'att': '!' * 512 * 1024 * 1024}  # 512mb
    small_data = {'event': datatypes.Event.Serialize(event2),
                  'att': '!' * 1024}  # 1kb

    # Use a queue to get the request object out of the thread.
    q = Queue.Queue()
    def PostBig():
      r = requests.post('http://localhost:' + str(self.port), files=big_data)
      q.put(r)
    t = threading.Thread(target=PostBig)
    t.daemon = False
    t.start()
    time.sleep(0.2)  # Give the big file thread a chance to start up.

    r = requests.post('http://localhost:' + str(self.port), files=small_data)
    t.join()

    self.assertEqual(200, r.status_code)
    self.assertEqual(200, q.get().status_code)
    self.assertEqual(2, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[0]))
    self.assertEqual('small', self.core.emit_calls[0][0]['size'])
    self.assertEqual(1, len(self.core.emit_calls[1]))
    self.assertEqual('big', self.core.emit_calls[1][0]['size'])

  def testCurlCommand(self):
    fd, att_path = tempfile.mkstemp(dir=self._tmp_dir)
    att = os.urandom(1024)  # 1kb
    with os.fdopen(fd, 'w') as f:
      f.write(att)
    os.system('curl -X POST -F \'event=[{"GG": "HH"}, {"att_id": "att"}]\' '
              '-F \'att=@%s\' localhost:%d' %
              (att_path, self.port))
    self.assertEqual(1, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[0]))
    self.assertEqual({'GG': 'HH'}, self.core.emit_calls[0][0].payload)
    with open(self.core.emit_calls[0][0].attachments['att_id']) as f:
      self.assertEqual(att, f.read())

  @unittest.skip('This test run too slow, please run it manually.')
  def testOneHugeAttachment(self):
    """Tests the ability to transfer one huge attachment."""
    # Since it can be slow to transfer 1 GB of data, only perform one
    # iteration of the test.
    att = '!' * 1024 * 1024 * 1024  # 1gb
    event = datatypes.Event({}, {'att_id': 'att'})
    data = {'event': datatypes.Event.Serialize(event),
            'att': att}
    r = requests.post('http://localhost:' + str(self.port), files=data)
    self.assertEqual(200, r.status_code)
    self.assertEqual(1, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[0]))
    with open(self.core.emit_calls[0][0].attachments['att_id']) as f:
      self.assertEqual(att, f.read())


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG, format=log_utils.LOG_FORMAT)
  unittest.main()
