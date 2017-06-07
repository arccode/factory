#!/usr/bin/python2
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for input HTTP plugin."""

from __future__ import print_function

import logging
import os
import shutil
import tempfile
import unittest

import requests

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import log_utils
from instalog import plugin_sandbox
from instalog import testing
from instalog.utils import net_utils


class TestInputHTTPTestlog(unittest.TestCase):

  def _CreatePlugin(self):
    self.core = testing.MockCore()
    self.hostname = 'localhost'
    self.port = net_utils.FindUnusedPort()
    config = {
        'hostname': 'localhost',
        'port': self.port}
    self.sandbox = plugin_sandbox.PluginSandbox(
        'input_http_testlog', config=config, core_api=self.core)
    self.sandbox.Start(True)
    self.plugin = self.sandbox._plugin  # pylint: disable=protected-access

  def setUp(self):
    self._CreatePlugin()
    self._tmp_dir = tempfile.mkdtemp(prefix='input_http_testlog_unittest_')

  def tearDown(self):
    if self.sandbox.GetState() != plugin_sandbox.DOWN:
      self.sandbox.Stop(True)
      self.assertTrue(self.core.AllStreamsExpired())
      self.core.Close()
    shutil.rmtree(self._tmp_dir)

  def _RequestsPost(self, files=None, multi_event=True, timeout=None):
    # To avoid requests use content-type application/x-www-form-urlencoded
    return requests.post(url='http://localhost:' + str(self.port), files=files,
                         headers={'Multi-Event': str(multi_event)},
                         timeout=timeout)

  def _ValidStationTestRunEvent(self):
    return datatypes.Event({
        'uuid': '8b127476-2604-422a-b9b1-f05e4f14bf72',
        'type': 'station.test_run',
        'apiVersion': '0.1',
        'time': '2017-01-05T13:01:45.503Z',
        'testRunId': '8b127472-4593-4be8-9e94-79f228fc1adc',
        'testName': 'the_test',
        'testType': 'aaaa',
        'arguments': {},
        'status': 'PASSED',
        'startTime': '2017-01-05T13:01:45.489Z',
    })

  def testInvalidSimpleEvent(self):
    att1 = os.urandom(1024)  # 1kb data
    att2 = os.urandom(1024)  # 1kb data
    event = self._ValidStationTestRunEvent()
    event['attachments'] = {'att_key1': {'path': '/path/to/file',
                                         'mimeType': 'text/plain'},
                            'att_key2': {'path': '/path/to/file',
                                         'mimeType': 'text/plain'}}
    data = {'event': datatypes.Event.Serialize(event),
            'att_key1': att1}
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(400, r.status_code)
    self.assertEqual('Bad request: ValueError("event[\'attachment\'] are not '
                     'consistent with attachments in requests.",)', r.reason)

    event['attachments'] = {'att_key1': {'path': '/path/to/file',
                                         'mimeType': 'text/plain'}}
    data = {'event': datatypes.Event.Serialize(event),
            'att_key1': att1,
            'att_key2': att2}
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(400, r.status_code)
    self.assertEqual('Bad request: ValueError("event[\'attachment\'] are not '
                     'consistent with attachments in requests.",)', r.reason)

    event['attachments'] = {}
    data = {'event': datatypes.Event.Serialize(event),
            'att_key1': att1}
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(400, r.status_code)
    self.assertEqual('Bad request: ValueError("event[\'attachment\'] are not '
                     'consistent with attachments in requests.",)', r.reason)

    event['attachments'] = {'att_key1': {'path': '/path/to/file',
                                         'mimeType': 'text/plain'}}
    data = {'event': datatypes.Event.Serialize(event)}
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(400, r.status_code)
    self.assertEqual('Bad request: ValueError("event[\'attachment\'] are not '
                     'consistent with attachments in requests.",)', r.reason)

  def testTestlogEventWithAttachments(self):
    # Should auto set event.attachments['att_key1']='att_key1'
    event = self._ValidStationTestRunEvent()
    event['attachments'] = {'att_key1': {'path': '/path/to/file',
                                         'mimeType': 'text/plain'}}
    att1 = os.urandom(1024)  # 1kb data
    data = {'event': datatypes.Event.Serialize(event),
            'att_key1': att1}
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(200, r.status_code)
    self.assertEqual(1, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[0]))
    # Input HTTP Testlog plugin will auto add __testlog__=True to event
    self.core.emit_calls[0][0].payload.pop('__testlog__')
    self.assertEqual(event.payload, self.core.emit_calls[0][0].payload)
    with open(self.core.emit_calls[0][0].attachments['att_key1']) as f:
      self.assertEqual(att1, f.read())

  def testTestlogEventWithoutAttachments(self):
    event = self._ValidStationTestRunEvent()
    data = {'event': datatypes.Event.Serialize(event)}
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(200, r.status_code)
    self.assertEqual(1, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[0]))
    # input http testlog plugin will auto add __testlog__=True to event
    self.core.emit_calls[0][0].payload.pop('__testlog__')
    self.assertEqual(event.payload, self.core.emit_calls[0][0].payload)
    event['arguments']['A'] = {'value': 'yoyo'}
    event['arguments']['B'] = {'value': 9.53543, 'description': 'a number'}
    event['arguments']['C'] = {'value': -9}
    event['failures'] = [{'code': 'C', 'details': 'D'}]
    event['serialNumbers'] = {'A': 'B'}
    event['parameters'] = {'A': {'description': 'D'}}
    event['series'] = {'A': {'description': 'D', 'data': [
        {'key': 987, 'status': 'PASS'},
        {'key': 7.8, 'status': 'FAIL'}]}}
    data = {'event': datatypes.Event.Serialize(event)}
    r = self._RequestsPost(files=data, multi_event=False)
    logging.info(r.reason)
    self.assertEqual(200, r.status_code)
    self.assertEqual(2, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[1]))
    # Input HTTP Testlog plugin will auto add __testlog__=True to event
    self.core.emit_calls[1][0].payload.pop('__testlog__')
    self.assertEqual(event.payload, self.core.emit_calls[1][0].payload)
    event['arguments']['D'] = {}
    data = {'event': datatypes.Event.Serialize(event)}
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(400, r.status_code)
    self.assertEqual('Bad request: SchemaException("Required item \'value\' '
                     'does not exist in FixedDict {}",)', r.reason)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO, format=log_utils.LOG_FORMAT)
  unittest.main()
