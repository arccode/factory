#!/usr/bin/env python3
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for input HTTP plugin."""

import logging
import os
import shutil
import tempfile
import time
import unittest

import requests

from cros.factory.instalog import datatypes
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_sandbox
from cros.factory.instalog import testing
from cros.factory.instalog.utils import net_utils


class TestInputHTTPTestlog(unittest.TestCase):

  def _CreatePlugin(self):
    self.core = testing.MockCore()
    self.hostname = 'localhost'
    self.port = net_utils.FindUnusedPort()
    config = {
        'hostname': 'localhost',
        'port': self.port,
        'log_level_threshold': logging.WARNING}
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
        'apiVersion': '0.21',
        'time': 1483592505.503,
        'testRunId': '8b127472-4593-4be8-9e94-79f228fc1adc',
        'testName': 'the_test',
        'testType': 'aaaa',
        'status': 'PASS',
        'startTime': 1483592505.489,
        'serialNumbers': {'serial_number': 'Test SN'},
    })

  def _ValidStationMessageEvent(self):
    return datatypes.Event({
        'uuid': '9209203a-0b07-4dff-948d-9b097de4206d',
        'type': 'station.message',
        'apiVersion': '0.21',
        'time': 1483592505.503,
        'message': 'THIS IS A MESSAGE',
        'logLevel': 'INFO',
        'testRunId': '8b127472-4593-4be8-9e94-79f228fc1adc',
    })

  def testMessageEvent(self):
    info_event = self._ValidStationMessageEvent()
    warning_event = self._ValidStationMessageEvent()
    warning_event['logLevel'] = 'WARNING'
    error_event = self._ValidStationMessageEvent()
    error_event['logLevel'] = 'ERROR'
    data = [('event', datatypes.Event.Serialize(info_event)),
            ('event', datatypes.Event.Serialize(warning_event)),
            ('event', datatypes.Event.Serialize(error_event))]
    r = self._RequestsPost(files=data)
    self.assertEqual(200, r.status_code)
    self.assertEqual(1, len(self.core.emit_calls))
    self.assertEqual(2, len(self.core.emit_calls[0]))
    self.assertEqual('WARNING', self.core.emit_calls[0][0]['logLevel'])
    self.assertEqual('ERROR', self.core.emit_calls[0][1]['logLevel'])

  def testOldVersionEvent(self):
    # Test simple Testlog event without attachment.
    event = datatypes.Event({
        'uuid': '8b127476-2604-422a-b9b1-f05e4f14bf72',
        'type': 'station.test_run',
        'apiVersion': '0.1',
        'time': {'value': '2017-01-05T13:01:45.503Z', '__type__': 'datetime'},
        'testRunId': '8b127472-4593-4be8-9e94-79f228fc1adc',
        'testName': 'the_test',
        'testType': 'aaaa',
        'status': 'PASSED',
        'startTime': '2017-01-05T13:01:45.489Z',
        'serialNumbers': {'serial_number': 'Test SN'},
    })
    data = {'event': datatypes.Event.Serialize(event)}
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(200, r.status_code)
    self.assertEqual(1, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[0]))
    self.assertEqual(self.core.emit_calls[0][0].payload, {
        '__testlog__': True,
        'status': 'PASS',
        'uuid': '8b127476-2604-422a-b9b1-f05e4f14bf72',
        'testType': 'aaaa',
        'testName': 'the_test',
        'apiVersion': '0.21',
        'startTime': 1483621305.489,
        # The time field is corrected.
        'time': self.core.emit_calls[0][0].payload['time'],
        'type': u'station.test_run',
        'serialNumbers': {'serial_number': 'Test SN'},
        'testRunId': u'8b127472-4593-4be8-9e94-79f228fc1adc'})

    # Test simple Testlog event with a attachment.
    event['attachments'] = {'att_key1': {'path': '/path/to/file',
                                         'mimeType': 'text/plain'}}
    att1 = os.urandom(1024)  # 1kb data
    data = {'event': datatypes.Event.Serialize(event),
            'att_key1': att1}
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(200, r.status_code)
    self.assertEqual(2, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[0]))
    self.assertEqual(self.core.emit_calls[1][0].payload, {
        '__testlog__': True,
        'status': 'PASS',
        'uuid': '8b127476-2604-422a-b9b1-f05e4f14bf72',
        'testType': 'aaaa',
        'testName': 'the_test',
        'apiVersion': '0.21',
        'startTime': 1483621305.489,
        # The time field is corrected.
        'time': self.core.emit_calls[1][0].payload['time'],
        'type': 'station.test_run',
        'testRunId': '8b127472-4593-4be8-9e94-79f228fc1adc',
        'serialNumbers': {'serial_number': 'Test SN'},
        'attachments': {
            'att_key1': {'path': '/path/to/file', 'mimeType': 'text/plain'}}})
    with open(self.core.emit_calls[1][0].attachments['att_key1'], 'rb') as f:
      self.assertEqual(att1, f.read())

    # Test complex Testlog event without attachment.
    del event.payload['attachments']
    event['arguments'] = {}
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
    self.assertEqual(200, r.status_code)
    self.assertEqual(3, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[2]))
    self.assertEqual(self.core.emit_calls[2][0].payload, {
        '__testlog__': True,
        'status': 'PASS',
        'uuid': '8b127476-2604-422a-b9b1-f05e4f14bf72',
        'testType': 'aaaa',
        'testName': 'the_test',
        'apiVersion': '0.21',
        'startTime': 1483621305.489,
        # The time field is corrected.
        'time': self.core.emit_calls[2][0].payload['time'],
        'type': u'station.test_run',
        'testRunId': u'8b127472-4593-4be8-9e94-79f228fc1adc',
        'arguments': {
            'A': {'value': '"yoyo"'},
            'B': {'description': 'a number', 'value': '9.53543'},
            'C': {'value': '-9'}},
        'failures': [{'code': 'C', 'details': 'D'}],
        'parameters': {
            'A_key': {
                'type': 'argument',
                'data': [{'numericValue': 987},
                         {'numericValue': 7.8}],
                'group': 'A'},
            'A_value': {
                'type': 'measurement',
                'data': [{'status': 'PASS'},
                         {'status': 'FAIL'}],
                'description': 'D',
                'group': 'A'},
            'parameter_A': {
                'type': 'measurement',
                'data': [{}],
                'description': 'D'}},
        'serialNumbers': {'A': 'B'}})

    # Test invalid Testlog event.
    event['arguments']['D'] = {}
    data = {'event': datatypes.Event.Serialize(event)}
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(400, r.status_code)
    self.assertEqual("Bad request: KeyError('value',)", r.reason)

  def testCorrectTime(self):
    event = self._ValidStationTestRunEvent()
    data = {'event': datatypes.Event.Serialize(event)}
    time_check = time.time()
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(200, r.status_code)
    self.assertEqual(1, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[0]))
    self.assertNotEqual(self.core.emit_calls[0][0]['time'], event['time'])
    self.assertGreater(self.core.emit_calls[0][0]['time'], time_check)

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
    # The time field is corrected.
    event['time'] = self.core.emit_calls[0][0].payload['time']
    self.assertEqual(event.payload, self.core.emit_calls[0][0].payload)
    with open(self.core.emit_calls[0][0].attachments['att_key1'], 'rb') as f:
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
    # The time field is corrected.
    self.core.emit_calls[0][0].payload['time'] = event['time']
    self.assertEqual(event.payload, self.core.emit_calls[0][0].payload)
    event['arguments'] = {}
    event['arguments']['A'] = {'value': '"yoyo"'}
    event['arguments']['B'] = {'value': '9.53543', 'description': 'a number'}
    event['arguments']['C'] = {'value': '-9'}
    event['failures'] = [{'code': 'C', 'details': 'D'}]
    event['serialNumbers'] = {'A': 'B'}
    event['parameters'] = {
        'A': {
            'description': 'D',
            'type': 'measurement',
            'data': [
                {'numericValue': 987, 'status': 'PASS'},
                {'serializedValue': '[7.8]'}]}}
    data = {'event': datatypes.Event.Serialize(event)}
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(200, r.status_code)
    self.assertEqual(2, len(self.core.emit_calls))
    self.assertEqual(1, len(self.core.emit_calls[1]))
    # Input HTTP Testlog plugin will auto add __testlog__=True to event
    self.core.emit_calls[1][0].payload.pop('__testlog__')
    # The time field is corrected.
    self.core.emit_calls[1][0].payload['time'] = event['time']
    self.assertEqual(event.payload, self.core.emit_calls[1][0].payload)
    event['arguments']['D'] = {}
    data = {'event': datatypes.Event.Serialize(event)}
    r = self._RequestsPost(files=data, multi_event=False)
    self.assertEqual(400, r.status_code)
    self.assertEqual('Bad request: SchemaException("Required item \'value\' '
                     'does not exist in FixedDict {}",)', r.reason)


if __name__ == '__main__':
  log_utils.InitLogging(log_utils.GetStreamHandler(logging.INFO))
  unittest.main()
