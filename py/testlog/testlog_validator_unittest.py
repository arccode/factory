#!/usr/bin/python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import datetime
import json
import logging
import os
import pprint
import shutil
import tempfile
import unittest

from testlog_pkg import testlog
from testlog_pkg import testlog_utils
from testlog_pkg import testlog_validator
from testlog_pkg.utils import schema
from testlog_pkg.utils import time_utils


class TestlogValidatorTest(unittest.TestCase):
  class TestEvent(testlog.EventBase):
    """A derived class from Event that can be initialized."""
    FIELDS = {
        'Long':    (True, testlog_validator.Validator.Long),
        'Number':  (True, testlog_validator.Validator.Number),
        'String':  (True, testlog_validator.Validator.String),
        'Boolean': (True, testlog_validator.Validator.Boolean),
        'Dict':    (True, testlog_validator.Validator.Dict),
        'List':    (True, testlog_validator.Validator.List),
        'Time':    (True, testlog_validator.Validator.Time),
    }
    @classmethod
    def GetEventType(cls):
      return 'unittest.Event'

    def CastFields(self):
      pass

  def testNonExistedField(self):
    event = self.TestEvent()
    with self.assertRaises(testlog_utils.TestlogError):
      event['CatchMeIfYouCan'] = 'GuessWhat'

  def testLongValidator(self):
    event = self.TestEvent()
    with self.assertRaises(ValueError):
      event['Long'] = '3333'
    with self.assertRaises(ValueError):
      event['Long'] = 'aaaa'
    event['Long'] = 3333
    self.assertEquals(event['Long'], 3333)

  def testNumberValidator(self):
    event = self.TestEvent()
    with self.assertRaises(ValueError):
      event['Number'] = '66'
    with self.assertRaises(ValueError):
      event['Number'] = 'aa'
    event['Number'] = 33.33
    self.assertAlmostEqual(event['Number'], 33.33)
    event['Number'] = -1
    self.assertAlmostEqual(event['Number'], -1)
    event['Number'] = 999999999999999
    self.assertAlmostEqual(event['Number'], 999999999999999)

  def testStringValidator(self):
    event = self.TestEvent()
    with self.assertRaises(ValueError):
      event['String'] = 6666
    event['String'] = '7777'
    self.assertEquals(event['String'], '7777')

  def testBooleanValidator(self):
    event = self.TestEvent()
    with self.assertRaises(ValueError):
      event['Boolean'] = None
    with self.assertRaises(ValueError):
      event['Boolean'] = 'False'
    event['Boolean'] = True
    self.assertEquals(event['Boolean'], True)

  def testDictValidator(self):
    event = self.TestEvent()
    # Feed a wrong format of dicitionary.
    with self.assertRaises(ValueError):
      event['Dict'] = {'key1': 'value1', 'key2': 'value2'}
    event['Dict'] = {'key': 'PARA1', 'value': 33}
    self.assertEquals(event['Dict'], {'PARA1': 33})
    # Feed a duplicated key.
    with self.assertRaises(ValueError):
      event['Dict'] = {'key': 'PARA1', 'value': 'PARA2'}
    # Put the second dictionary
    event['Dict'] = {'key': 'PARA2', 'value': 'aaa'}
    self.assertEquals(event['Dict'],
                      {'PARA1': 33, 'PARA2': 'aaa'})
    # Converts to JSON and convert back.
    event2 = testlog.EventBase.FromJSON(event.ToJSON(), False)
    self.assertEquals(event, event2)

  def testListValidator(self):
    event = self.TestEvent()
    event['List'] = 123
    event['List'] = '456'
    self.assertEquals(event['List'], [123, '456'])

  def testTimeValidator(self):
    event = self.TestEvent()
    # Validator.Time accepts string or datetime.datetime.
    with self.assertRaises(ValueError):
      event['Time'] = datetime.date(1867, 7, 1)  # Canada's Birthday
    valid_datetime = datetime.datetime(1986, 11, 5, 1, 24, 0)
    event['Time'] = valid_datetime
    self.assertEquals(event['Time'], copy.copy(valid_datetime))


class StationTestRunFieldsValidatorTest(unittest.TestCase):
  """Checks the correctness of FIELDS' validator and SCHEMA's"""

  def testArgumentValidator(self):
    event = testlog.StationTestRun()
    # Valid argument
    event['arguments'] = {'key': 'KeyIsAString', 'value': {
        'value': 'This is a string.'}}
    event['arguments'] = {'key': 'KeyIsANumber', 'value': {
        'value': 987.654321,
        'description': 'G'}}
    event['arguments'] = {'key': 'KeyCanBeAnything', 'value': {
        'value': True}}
    # Wrong top-level type
    with self.assertRaises(schema.SchemaException):
      event['arguments'] = {'key': 'A', 'value': 'Google'}
    # Wrong key type
    with self.assertRaises(ValueError):
      event['arguments'] = {'key': 3, 'value': {'value': 0}}
    # Additional item in Dict
    with self.assertRaises(schema.SchemaException):
      event['arguments'] = {'key': 'A', 'value': {'value': 0, 'A': 'B'}}
    # Missing item
    with self.assertRaises(schema.SchemaException):
      event['arguments'] = {'key': 'A', 'value': {'description': 'yoyo'}}
    # Empty dict
    with self.assertRaises(schema.SchemaException):
      event['arguments'] = {'key': 'A', 'value': {}}

  def testFailuresValidator(self):
    event = testlog.StationTestRun()
    # Valid failure
    event['failures'] = {
        'code': 'WiFiThroughputSpeedLimitFail',
        'details': '2.4G WiFi throughput test fail: ... bla bla bla'}
    # Wrong top-level type
    with self.assertRaises(schema.SchemaException):
      event['failures'] = 'Google'
    # Wrong value type
    with self.assertRaises(schema.SchemaException):
      event['failures'] = {'code': 'C', 'details': 3}
    # Additional item in Dict
    with self.assertRaises(schema.SchemaException):
      event['failures'] = {'code': 'C', 'details': 'D', 'A': 'B'}
    # Missing item
    with self.assertRaises(schema.SchemaException):
      event['failures'] = {'code': 'C'}
    # Empty dict
    with self.assertRaises(schema.SchemaException):
      event['failures'] = {}

  def testSerialNumbersValidator(self):
    event = testlog.StationTestRun()
    # Valid serial number
    event['serialNumbers'] = {'key': 'mlb', 'value': 'A1234567890'}
    event['serialNumbers'] = {'key': 'sn', 'value': None}
    # Wrong key type
    with self.assertRaises(ValueError):
      event['serialNumbers'] = {'key': 3, 'value': 'Google'}
    # Wrong value type
    with self.assertRaises(schema.SchemaException):
      event['serialNumbers'] = {'key': 'A', 'value': {}}
    with self.assertRaises(schema.SchemaException):
      event['serialNumbers'] = {'key': 'A', 'value': 3}

  def testParametersValidator(self):
    event = testlog.StationTestRun()
    # Valid parameter
    event['parameters'] = {'key': 'a', 'value': {}}
    event['parameters'] = {'key': 'b', 'value': {'status': 'PASS'}}
    event['parameters'] = {'key': 'ec_firmware_version', 'value': {
        'description': 'Version of the EC firmware on the DUT.',
        'group': 'What is this?',
        'status': 'FAIL',
        'valueUnit': 'version',
        'numericValue': 0,
        'expectedMinimum': 1.2,
        'expectedMaximum': 3L,
        'textValue': '1.56a',
        'expectedRegex': '^1.5'
    }}
    # Wrong top-level type
    with self.assertRaises(schema.SchemaException):
      event['parameters'] = {'key': 'A', 'value': 'Google'}
    # Wrong key type
    with self.assertRaises(ValueError):
      event['parameters'] = {'key': 3, 'value': {}}
    # Wrong value type
    with self.assertRaises(schema.SchemaException):
      event['parameters'] = {'key': 'A', 'value': {'description': 0}}
    with self.assertRaises(schema.SchemaException):
      event['parameters'] = {'key': 'A', 'value': {'numericValue': 'Google'}}
    # Value not in choices(PASS, FAIL)
    with self.assertRaises(schema.SchemaException):
      event['parameters'] = {'key': 'A', 'value': {'status': 'Google'}}
    # Additional item in Dict
    with self.assertRaises(schema.SchemaException):
      event['parameters'] = {'key': 'A', 'value': {'NonExist': 'Hi'}}

  def testSeriesValidator(self):
    event = testlog.StationTestRun()
    # Valid parameter
    event['series'] = {'key': 'a', 'value': {}}
    event['series'] = {'key': 'b', 'value': {'status': 'PASS', 'data': []}}
    event['series'] = {'key': '5g_throughput', 'value': {
        'description': '5G throughput speeds at an interval of 1 per ... .',
        'group': 'Still do not know.',
        'status': 'FAIL',
        'keyUnit': 'second',
        'valueUnit': 'MBit/s',
        'data': [
            {
                'key': 1,
                'status': 'FAIL',
                'numericValue': 19.8,
                'expectedMinimum': 20,
                'expectedMaximum': 999L
            }, {
                'key': 2.0,
                'status': 'PASS'
            }
        ]
    }}
    # Wrong top-level type, value should be a Dict
    with self.assertRaises(schema.SchemaException):
      event['series'] = {'key': 'A', 'value': 'Google'}
    # Wrong second-level type, data should be a List
    with self.assertRaises(schema.SchemaException):
      event['series'] = {'key': 'A', 'value': {'data': 'Google'}}
    with self.assertRaises(schema.SchemaException):
      event['series'] = {'key': 'A', 'value': {'data': {}}}
    # Wrong key type
    with self.assertRaises(ValueError):
      event['series'] = {'key': 3, 'value': {}}
    # Wrong value type
    with self.assertRaises(schema.SchemaException):
      event['series'] = {'key': 'A', 'value': {'description': 0}}
    with self.assertRaises(schema.SchemaException):
      event['series'] = {'key': 'A', 'value': {'data': [{'key': 'Google'}]}}
    with self.assertRaises(schema.SchemaException):
      event['series'] = {'key': 'A', 'value': {
          'data': [{'key': 0, 'status': 0}]}}
    # Value not in choices(PASS, FAIL)
    with self.assertRaises(schema.SchemaException):
      event['series'] = {'key': 'A', 'value': {'status': 'Google'}}
    with self.assertRaises(schema.SchemaException):
      event['series'] = {'key': 'A', 'value': {
          'data': [{'key': 0, 'status': 'Google'}]}}
    # Additional item in Dict
    with self.assertRaises(schema.SchemaException):
      event['series'] = {'key': 'A', 'value': {'NonExist': 'Hi'}}
    with self.assertRaises(schema.SchemaException):
      event['series'] = {'key': 'A', 'value': {
          'data': [{'key': 0, 'A': 'B'}]}}
    # Missing item
    with self.assertRaises(schema.SchemaException):
      event['series'] = {'key': 'A', 'value': {'data': [{}]}}


class StationTestRunApiValidatorTest(unittest.TestCase):
  """Validators primarily serve for StationTestRun."""

  def setUp(self):
    self.state_dir = tempfile.mkdtemp()
    self.tmp_dir = tempfile.mkdtemp()
    # Reset testlog if any
    # pylint: disable=protected-access
    if testlog._global_testlog:
      testlog._global_testlog.Close()

  def tearDown(self):
    shutil.rmtree(self.state_dir)
    shutil.rmtree(self.tmp_dir)

  def _SimulateSubSession(self):
    # Prepare the attachments_folder by initializing testlog as a sub session
    session_json_path = testlog.InitSubSession(
        log_root=self.state_dir,
        station_test_run=testlog.StationTestRun(),
        uuid=time_utils.TimedUUID())
    os.environ[testlog.TESTLOG_ENV_VARIABLE_NAME] = session_json_path
    return session_json_path

  def testParam(self):
    self._SimulateSubSession()
    testlog.LogParam(name='text', value='unittest',
                     description='None', value_unit='pcs')
    last_test_run = testlog.GetGlobalTestlog().last_test_run
    parameters = last_test_run['parameters']
    self.assertIn('text', parameters)
    self.assertEquals('unittest', parameters['text']['textValue'])
    self.assertEquals('None', parameters['text']['description'])
    self.assertEquals('pcs', parameters['text']['valueUnit'])

    testlog.LogParam(name='num', value=3388)
    self.assertIn('num', parameters)
    self.assertEquals(3388, parameters['num']['numericValue'])

    with self.assertRaisesRegexp(ValueError, 'numeric or text'):
      testlog.LogParam(name='oops', value=[1, 2, 3])

    with self.assertRaisesRegexp(ValueError, 'with numeric limits'):
      testlog.CheckParam(name='oops', value='yoha', min=30)

    with self.assertRaisesRegexp(ValueError, 'with regular expression'):
      testlog.CheckParam(name='oops', value=30, regex='yoha')

    self.assertTrue(
        testlog.CheckParam(name='InRange0', value=30, min=30))
    self.assertFalse(
        testlog.CheckParam(name='InRange1', value=30, max=29))
    self.assertTrue(
        testlog.CheckParam(name='Regex0', value='oops', regex='o.*s'))
    self.assertFalse(
        testlog.CheckParam(name='Regex1', value='oops', regex='y.*a'))
    self.assertTrue(
        testlog.CheckParam(
            name='Regex2', value='Hello world', regex='^H.*d$'))
    self.assertFalse(
        testlog.CheckParam(
            name='Regex3', value='--Hello world--', regex='^H.*d$'))
    self.assertTrue(
        testlog.CheckParam(
            name='Regex4', value='--Hello world--', regex='H.*d'))

  def testCreateSeries(self):
    session_json_path = self._SimulateSubSession()
    s1 = testlog.CreateSeries(name='s1')
    s1.LogValue(key=1988, value=1234)

    # Duplicate series name
    with self.assertRaisesRegexp(ValueError, 'duplicated'):
      s2 = testlog.CreateSeries(name='s1')
    # Not a numeric
    with self.assertRaisesRegexp(ValueError, 'numeric'):
      s1.LogValue(key='1988', value=1234)
    with self.assertRaisesRegexp(ValueError, 'numeric'):
      s1.LogValue(key=1988, value='1234')

    # Test float type
    s1.LogValue(key=1987.5, value=5678.0)

    s2 = testlog.CreateSeries(name='s2', description='withUnit',
                              key_unit='MHz', value_unit='dBm')
    s2.LogValue(key=2300, value=31.5)
    # Give a range to fail.
    s2.CheckValue(key=2305, value=31.5, min=None, max=30)
    # The key is not checked for duplication as it is a list.
    # Expect to see a FAIL and a PASS in the series of same key.
    s2.CheckValue(key=2305, value=30.5, min=None, max=31)

    logging.info('Load back JSON:\n%s\n',
                 pprint.pformat(json.loads(open(session_json_path).read())))

  def testAttachmentValidator(self):
    self._SimulateSubSession()

    TEST_STR = 'Life is a maze and love is a riddle'
    TEST_FILENAME = 'TextFile.txt'
    test_run = testlog.StationTestRun()
    def CreateTextFile():
      path = os.path.join(self.tmp_dir, TEST_FILENAME)
      with open(path, 'w') as fd:
        fd.write(TEST_STR)
      return path

    # Move a file normally.
    file_to_attach = CreateTextFile()
    test_run.AttachFile(
        path=os.path.realpath(file_to_attach),
        name='text1',
        mime_type='text/plain')
    # Missing mime_type
    file_to_attach = CreateTextFile()
    with self.assertRaisesRegexp(ValueError, 'mime'):
      test_run.AttachFile(
          path=os.path.realpath(file_to_attach),
          name='text1',
          mime_type=None)
    # mime_type with incorrect format
    with self.assertRaisesRegexp(ValueError, 'mime'):
      test_run.AttachFile(
          path=os.path.realpath(file_to_attach),
          name='text1',
          mime_type='wrong_mime_format')
    # Incorret path
    file_to_attach = CreateTextFile()
    with self.assertRaisesRegexp(ValueError, 'find file'):
      test_run.AttachFile(
          path=os.path.realpath(file_to_attach) + 'abcd',
          name='text1',
          mime_type='text/plain')
    # Duplicate name
    file_to_attach = CreateTextFile()
    with self.assertRaisesRegexp(ValueError, 'duplicated'):
      test_run.AttachFile(
          path=os.path.realpath(file_to_attach),
          name='text1',
          mime_type='text/plain')
    # Name duplication on target folder
    file_to_attach = CreateTextFile()
    test_run.AttachFile(
        path=os.path.realpath(file_to_attach),
        name='text2',
        mime_type='text/plain')
    # Examine the result
    paths = set()
    for item in test_run['attachments'].itervalues():
      path = item['path']
      text = open(path, 'r').read()
      self.assertEquals(TEST_STR, text)
      self.assertTrue(TEST_FILENAME in path)
      paths.add(path)
    # Make sure the file names are distinguished
    self.assertEquals(len(paths), 2)

  def testFromDict(self):
    self._SimulateSubSession()
    example_dict = {
        'uuid': '8b127476-2604-422a-b9b1-f05e4f14bf72',
        'type': 'station.test_run',
        'apiVersion': '0.1',
        'time': '2017-01-05T13:01:45.503Z',
        'seq': 8202191,
        'stationDeviceId': 'e7d3227e-f12d-42b3-9c64-0d9e8fa02f6d',
        'stationInstallationId': '92228272-056e-4329-a432-64d3ed6dfa0c',
        'testRunId': '8b127472-4593-4be8-9e94-79f228fc1adc',
        'testName': 'the_test',
        'testType': 'aaaa',
        'arguments': {},
        'status': 'PASSED',
        'startTime': '2017-01-05T13:01:45.489Z',
        'failures': [],
        'parameters': {},
        'series': {}
    }
    _unused_valid_event = testlog.EventBase.FromDict(example_dict)
    example_dict['arguments']['A'] = {'value': 'yoyo'}
    example_dict['arguments']['B'] = {'value': 9.53543, 'description': 'number'}
    example_dict['arguments']['C'] = {'value': -9}
    example_dict['failures'].append({'code': 'C', 'details': 'D'})
    example_dict['serialNumbers'] = {}
    example_dict['serialNumbers']['A'] = 'B'
    example_dict['parameters']['A'] = {'description': 'D'}
    example_dict['series']['A'] = {'description': 'D', 'data': [
        {'key': 987, 'status': 'PASS'},
        {'key': 7.8, 'status': 'FAIL'}]}
    _unused_valid_event = testlog.EventBase.FromDict(example_dict)
    with self.assertRaises(schema.SchemaException):
      example_dict['arguments']['D'] = {}
      _unused_invalid_event = testlog.EventBase.FromDict(example_dict)


if __name__ == '__main__':
  logging.basicConfig(
      format=('[%(levelname)s] '
              ' %(threadName)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=logging.INFO,
      datefmt='%Y-%m-%d %H:%M:%S')
  unittest.main()
