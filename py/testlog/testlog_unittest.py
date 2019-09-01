#!/usr/bin/env python2
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
import subprocess
import tempfile
import time
import unittest

from testlog_pkg import testlog
from testlog_pkg import testlog_utils
from testlog_pkg.utils import file_utils
from testlog_pkg.utils import json_utils
from testlog_pkg.utils import schema
from testlog_pkg.utils import time_utils


SAMPLE_DATETIME_FLOAT = 618538088.888888
SAMPLE_DATETIME = datetime.datetime(1989, 8, 8, 8, 8, 8, 888888)
SAMPLE_DATETIME_STRING = '618538088.888888'


class TestlogTestBase(unittest.TestCase):

  def setUp(self):
    self.tmp_dir = tempfile.mkdtemp()
    self.state_dir = tempfile.mkdtemp()
    self.session_uuid = None

  def tearDown(self):
    shutil.rmtree(self.state_dir)
    shutil.rmtree(self.tmp_dir)
    self._reset()

  def _reset(self):
    """Deletes state files and resets global variables."""
    # pylint: disable=protected-access
    if testlog._global_testlog:
      testlog._global_testlog.Close()
    file_utils.TryUnlink(testlog._SEQUENCE_PATH)
    if testlog.TESTLOG_ENV_VARIABLE_NAME in os.environ:
      del os.environ[testlog.TESTLOG_ENV_VARIABLE_NAME]

  def _SimulateSubSession(self):
    # Prepare the attachments_folder by initializing testlog as a sub session
    def _GetDUTDeviceID():
      logging.debug('DEBUG')
      return 'ThisIsDUTDeviceID'

    def _GetStationDeviceID():
      logging.warning('WARNING')
      return 'ThisIsStationDeviceID'

    def _GetInstallationID():
      logging.info('INFO')
      return 'ThisIsInstallationID'

    self.session_uuid = time_utils.TimedUUID()
    session_test_run = testlog.StationTestRun({
        'dutDeviceId': _GetDUTDeviceID(),
        'stationDeviceId': _GetStationDeviceID(),
        'stationInstallationId': _GetInstallationID(),
        'testRunId': self.session_uuid,
        'testType': 'TestlogDemo',
        'testName': 'TestlogDemo.Test',
        'status': testlog.StationTestRun.STATUS.STARTING,
        'startTime': SAMPLE_DATETIME_FLOAT,
        'serialNumbers': {'serial_number': 'TestlogDemo'}
    })

    session_json_path = testlog.InitSubSession(
        log_root=self.state_dir,
        station_test_run=session_test_run,
        uuid=self.session_uuid)
    os.environ[testlog.TESTLOG_ENV_VARIABLE_NAME] = session_json_path
    return session_json_path

  def _GetSampleTestRunEvent(self):
    return testlog.StationTestRun({
        'uuid': '8b127476-2604-422a-b9b1-f05e4f14bf72',
        'apiVersion': '0.21',
        'time': SAMPLE_DATETIME_FLOAT,
        'testRunId': '8b127472-4593-4be8-9e94-79f228fc1adc',
        'testName': 'the_test',
        'testType': 'aaaa',
        'status': 'PASS',
        'startTime': SAMPLE_DATETIME_FLOAT
    })


class TestlogTest(TestlogTestBase):

  def testDisallowRecursiveLogging(self):
    """Checks that calling 'logging' within log processing code is dropped."""
    logged_events = []
    def CheckMessage(event):
      logged_events.append(event)
      logging.info('testing 456')
    testlog.CapturePythonLogging(callback=CheckMessage)
    logging.info('testing 123')
    self.assertEquals(len(logged_events), 1)
    self.assertEquals(logged_events[0]['message'], 'testing 123')


class TestlogEventTest(TestlogTestBase):

  def testDisallowInitializeFakeEventClasses(self):
    with self.assertRaisesRegexp(
        testlog_utils.TestlogError, 'initialize directly'):
      testlog.EventBase()
    with self.assertRaisesRegexp(
        testlog_utils.TestlogError, 'initialize directly'):
      testlog.Event()
    with self.assertRaisesRegexp(
        testlog_utils.TestlogError, 'initialize directly'):
      testlog._StationBase()  # pylint: disable=protected-access

  def testEventSerializeUnserialize(self):
    original = testlog.StationInit()
    output = testlog.Event.FromJSON(original.ToJSON(), False)
    self.assertEquals(output, original)

  def testNewEventTime(self):
    event = testlog.StationInit({'time': SAMPLE_DATETIME_FLOAT})
    self.assertEquals(event['time'], SAMPLE_DATETIME_FLOAT)
    with self.assertRaises(ValueError):
      event = testlog.StationInit({'time': None})
    event = testlog.StationTestRun({
        'parameters': {
            'A': {
                'group': 'GROUP',
                'data': [{'numericValue': 1}]},
            'B': {
                'group': 'GROUP',
                'data': [{'numericValue': 2}, {'numericValue': 3}]}}
    })

  def testPopulateReturnsSelf(self):
    event = testlog.StationInit()
    self.assertIs(event.Populate({}), event)

  def testInvalidStatusTestRun(self):
    with self.assertRaises(ValueError):
      testlog.StationTestRun({'status': True})

  def testCheckIsValid(self):
    event = testlog.StationInit()
    event['failureMessage'] = 'Missed fields'
    event['apiVersion'] = '0.21'
    with self.assertRaisesRegexp(
        testlog_utils.TestlogError,
        'Missing fields: \\[\'count\', \'success\', \'uuid\', \'time\'\\]'):
      event.CheckIsValid()

    event = self._GetSampleTestRunEvent()
    event['apiVersion'] = '0.05'

    with self.assertRaisesRegexp(
        testlog_utils.TestlogError,
        'Invalid Testlog API version: 0.05'):
      event.CheckIsValid()

    event['apiVersion'] = '0.21'
    event.CheckIsValid()
    event['attachments'] = {'key': 'att_key1',
                            'value': {'path': '/path/to/file',
                                      'mimeType': 'text/plain'}}
    with self.assertRaisesRegexp(
        testlog_utils.TestlogError,
        r"Missing fields: \['serialNumbers'\]"):
      event.CheckIsValid()

    event['serialNumbers'] = {'key': 'A KEY', 'value': 'SN'}
    event.CheckIsValid()

    group_checker = event.GroupParam('GROUP', ['A', 'B'])
    with group_checker:
      event.LogParam('A', 1)
      event.LogParam('B', 2)
    event.CheckIsValid()
    event['parameters']['A']['data'].append({'numericValue': 3})
    with self.assertRaisesRegexp(
        testlog_utils.TestlogError,
        r'The parameters length in the group\(GROUP\) are not the same'):
      event.CheckIsValid()

  def testAddArgument(self):
    event = testlog.StationTestRun()
    event.AddArgument('K1', 'V1')
    event.AddArgument('K2', 2.2, 'D2')
    self.assertEquals(
        testlog.StationTestRun({
            'arguments': {
                'K1': {'value': '"V1"'},
                'K2': {'value': '2.2', 'description': 'D2'}}}),
        event)

  def testAddSerialNumber(self):
    event = testlog.StationTestRun()
    event.AddSerialNumber('K1', 'V1')
    self.assertEquals(
        testlog.StationTestRun({
            'serialNumbers': {
                'K1': 'V1'}}),
        event)
    event.AddSerialNumber('K2', 'SN')
    self.assertEquals(
        testlog.StationTestRun({
            'serialNumbers': {
                'K1': 'V1',
                'K2': 'SN'}}),
        event)

  def testParameters(self):
    event = testlog.StationTestRun()
    group_checker = event.GroupParam('GG', ['num', 'text'])
    with self.assertRaisesRegexp(
        ValueError,
        r'The grouped parameter should be used in the GroupChecker'):
      event.LogParam(name='num', value=3388)
    with self.assertRaisesRegexp(
        ValueError,
        r'The grouped parameter should be used in the GroupChecker'):
      event.LogParam(name='text', value='unittest')

    event.UpdateParam('text', description='TEST UPDATE')
    with group_checker:
      event.LogParam(name='text', value='unittest')
      event.LogParam(name='num', value=3388)
    event.LogParam(name='list', value=[1, 2, 3])

    with self.assertRaisesRegexp(
        ValueError,
        r'parameter\(text\) should not have data before grouping'):
      # pylint: disable=unused-variable
      invalid_group_checker = event.GroupParam('GG', ['text', 'what'])

    self.assertEqual(
        testlog.StationTestRun({
            'parameters': {
                'text': {
                    'group': 'GG',
                    'description': 'TEST UPDATE',
                    'type': 'measurement',
                    'data': [
                        {'textValue': 'unittest'}]},
                'num': {
                    'group': 'GG',
                    'type': 'measurement',
                    'data': [
                        {'numericValue': 3388}]},
                'list': {
                    'type': 'measurement',
                    'data': [
                        {'serializedValue': '[1, 2, 3]'}]}}}),
        event)

    with group_checker:
      event.LogParam(name='text', value='unittest2')
      event.LogParam(name='num', value=3389)
    event.LogParam(name='list', value={'1': 2, '3': [4]})

    with group_checker:
      event.CheckTextParam(name='text', value='= =', regex=r'[\^\<]_[^=]')
      event.CheckTextParam(name='text', value='^_<', regex=r'[\^\<]_[^=]')
      event.CheckNumericParam(name='num', value=3390, min=0)
      event.CheckNumericParam(name='num', value=3391, max=0)
    event.UpdateParam('list', description='TEST UPDATE2', value_unit='UNIT')

    self.assertEqual(
        testlog.StationTestRun({
            'parameters': {
                'text': {
                    'group': 'GG',
                    'description': 'TEST UPDATE',
                    'type': 'measurement',
                    'data': [
                        {'textValue': 'unittest'},
                        {'textValue': 'unittest2'},
                        {'textValue': '= =', 'expectedRegex': r'[\^\<]_[^=]',
                         'status': 'FAIL'},
                        {'textValue': '^_<', 'expectedRegex': r'[\^\<]_[^=]',
                         'status': 'PASS'}]},
                'num': {
                    'group': 'GG',
                    'type': 'measurement',
                    'data': [
                        {'numericValue': 3388},
                        {'numericValue': 3389},
                        {'numericValue': 3390, 'expectedMinimum': 0,
                         'status': 'PASS'},
                        {'numericValue': 3391, 'expectedMaximum': 0,
                         'status': 'FAIL'}]},
                'list': {
                    'description': 'TEST UPDATE2',
                    'valueUnit': 'UNIT',
                    'type': 'measurement',
                    'data': [
                        {'serializedValue': '[1, 2, 3]'},
                        {'serializedValue': '{"1": 2, "3": [4]}'}]}}}),
        event)

    with self.assertRaisesRegexp(ValueError, 'is not a numeric'):
      event.CheckNumericParam(name='oops', value='yoha')

    with self.assertRaisesRegexp(ValueError, 'is not a text'):
      event.CheckTextParam(name='oops', value=30)

    self.assertTrue(
        event.CheckNumericParam(name='InRange0', value=30, min=30))
    self.assertFalse(
        event.CheckNumericParam(name='InRange1', value=30, max=29))
    self.assertTrue(
        event.CheckTextParam(name='Regex0', value='oops', regex='o.*s'))
    self.assertFalse(
        event.CheckTextParam(name='Regex1', value='oops', regex='y.*a'))
    self.assertTrue(
        event.CheckTextParam(
            name='Regex2', value='Hello world', regex='^H.*d$'))
    self.assertFalse(
        event.CheckTextParam(
            name='Regex3', value='--Hello world--', regex='^H.*d$'))
    self.assertTrue(
        event.CheckTextParam(
            name='Regex4', value='--Hello world--', regex='H.*d'))

    with self.assertRaisesRegexp(
        ValueError,
        r'The parameters length in the group\(GG\) are not the same'):
      with group_checker:
        event.LogParam(name='num', value=3388)
        event.LogParam(name='list', value=[1, 2, 3])
        event.LogParam(name='list', value=[1, 2, 3])

    with self.assertRaises(IOError):
      with group_checker:
        event.LogParam(name='num', value=3388)
        raise IOError()

  def testAttachFileAndAttachContent(self):
    self._SimulateSubSession()
    CONTENT = 'Life is a maze and love is a riddle'
    DESCRIPTION = 'Unittest'
    TEST_FILENAME = 'TextFile.txt'
    event = testlog.StationTestRun()
    def CreateTextFile():
      path = os.path.join(self.tmp_dir, TEST_FILENAME)
      with open(path, 'w') as fd:
        fd.write(CONTENT)
      return path

    # Move a file normally.
    file_to_attach = CreateTextFile()
    event.AttachFile(
        path=os.path.realpath(file_to_attach),
        name='text1',
        mime_type='text/plain',
        description=DESCRIPTION)
    # Missing mime_type
    file_to_attach = CreateTextFile()
    with self.assertRaisesRegexp(ValueError, 'mime'):
      event.AttachFile(
          path=os.path.realpath(file_to_attach),
          name='text1',
          mime_type=None)
    # mime_type with incorrect format
    with self.assertRaisesRegexp(ValueError, 'mime'):
      event.AttachFile(
          path=os.path.realpath(file_to_attach),
          name='text1',
          mime_type='wrong_mime_format')
    # Incorret path
    file_to_attach = CreateTextFile()
    with self.assertRaisesRegexp(ValueError, 'find file'):
      event.AttachFile(
          path=os.path.realpath(file_to_attach) + 'abcd',
          name='text1',
          mime_type='text/plain')
    # Duplicate name
    file_to_attach = CreateTextFile()
    with self.assertRaisesRegexp(ValueError, 'duplicated'):
      event.AttachFile(
          path=os.path.realpath(file_to_attach),
          name='text1',
          mime_type='text/plain')
    # Name duplication on target folder
    file_to_attach = CreateTextFile()
    event.AttachFile(
        path=os.path.realpath(file_to_attach),
        name='text2',
        mime_type='text/plain',
        description=DESCRIPTION)
    # Attach content
    file_to_attach = CreateTextFile()
    event.AttachContent(
        content=CONTENT,
        name='text3',
        description=DESCRIPTION)
    # Examine the result
    paths = set()
    for att_name, att_dict in event['attachments'].iteritems():
      description = att_dict['description']
      self.assertEquals(DESCRIPTION, description)
      path = att_dict['path']
      text = open(path, 'r').read()
      self.assertEquals(CONTENT, text)
      self.assertTrue(att_name in path)
      paths.add(path)
    # Make sure the file names are distinguished
    self.assertEquals(len(paths), 3)

  def testStationTestRunWrapperInSession(self):
    session_json_path = self._SimulateSubSession()
    testlog.AddSerialNumber('KKK', 'SN')

    testlog.AddArgument('K1', 'V1')
    testlog.AddArgument('K2', 2.2, 'D2')

    group_checker = testlog.GroupParam('GROUP', ['A', 'B'])
    with group_checker:
      testlog.LogParam('A', 1)
      testlog.LogParam('B', 2)

    testlog.LogParam(name='text', value='unittest')
    testlog.UpdateParam(name='text', description='None', value_unit='pcs')
    testlog.LogParam(name='num', value=3388)

    testlog.LogParam('s1', 1234)
    testlog.LogParam('s1', 5678.0)
    testlog.UpdateParam('s2', description='withUnit', value_unit='dBm')
    testlog.LogParam('s2', 31.5)
    testlog.CheckNumericParam('s2', 31.5, max=30)
    testlog.CheckNumericParam('s2', 30.5, max=31)

    CONTENT = 'Life is a maze and love is a riddle'
    TEST_FILENAME = 'TextFile.txt'
    def CreateTextFile():
      path = os.path.join(self.tmp_dir, TEST_FILENAME)
      with open(path, 'w') as fd:
        fd.write(CONTENT)
      return path

    # Move a file normally.
    file_to_attach = CreateTextFile()
    testlog.AttachFile(
        path=os.path.realpath(file_to_attach),
        name='text1',
        mime_type='text/plain')
    # Attach content
    file_to_attach = CreateTextFile()
    testlog.AttachContent(
        content=CONTENT,
        name='text2')

    # Wait the thread update the session json file.
    time.sleep(0.5)
    event = json_utils.LoadFile(session_json_path)
    self.assertEqual(
        event['serialNumbers'],
        {'KKK': 'SN', 'serial_number': 'TestlogDemo'}
    )
    self.assertEqual(
        event['arguments'],
        {
            'K1': {'value': '"V1"'},
            'K2': {'value': '2.2', 'description': 'D2'}})
    self.assertEqual(
        event['parameters'],
        {
            'A': {
                'type': 'measurement',
                'group': 'GROUP',
                'data': [{'numericValue': 1}]},
            'B': {
                'type': 'measurement',
                'group': 'GROUP',
                'data': [{'numericValue': 2}]},
            'text': {
                'valueUnit': 'pcs',
                'description': 'None',
                'type': 'measurement',
                'data': [
                    {'textValue': 'unittest'}]},
            'num': {
                'type': 'measurement',
                'data': [
                    {'numericValue': 3388}]},
            's1': {
                'type': 'measurement',
                'data': [
                    {'numericValue': 1234},
                    {'numericValue': 5678.0}]},
            's2': {
                'valueUnit': 'dBm',
                'description': 'withUnit',
                'type': 'measurement',
                'data': [
                    {'numericValue': 31.5},
                    {
                        'status': 'FAIL',
                        'numericValue': 31.5,
                        'expectedMaximum': 30},
                    {
                        'status': 'PASS',
                        'numericValue': 30.5,
                        'expectedMaximum': 31}]}})
    paths = set()
    for att_name, att_dict in event['attachments'].iteritems():
      path = att_dict['path']
      text = open(path, 'r').read()
      self.assertEquals(CONTENT, text)
      self.assertTrue(att_name in path)
      paths.add(path)
    # Make sure the file names are distinguished
    self.assertEquals(len(paths), 2)

  def testFromDict(self):
    example_dict = {
        'uuid': '8b127476-2604-422a-b9b1-f05e4f14bf72',
        'type': 'station.test_run',
        'apiVersion': '0.21',
        'time': SAMPLE_DATETIME_FLOAT,
        'seq': 8202191,
        'stationDeviceId': 'e7d3227e-f12d-42b3-9c64-0d9e8fa02f6d',
        'stationInstallationId': '92228272-056e-4329-a432-64d3ed6dfa0c',
        'testRunId': '8b127472-4593-4be8-9e94-79f228fc1adc',
        'testName': 'the_test',
        'testType': 'aaaa',
        'arguments': {},
        'status': 'PASS',
        'startTime': SAMPLE_DATETIME_FLOAT,
    }
    with self.assertRaisesRegexp(testlog_utils.TestlogError,
                                 'Empty dict is invalid'):
      _unused_invalid_event = testlog.EventBase.FromDict(example_dict)
    del example_dict['arguments']
    _unused_valid_event = testlog.EventBase.FromDict(example_dict)
    example_dict['arguments'] = {}
    example_dict['arguments']['A'] = {'value': 'yoyo'}
    example_dict['arguments']['B'] = {'value': '9.53543', 'description': '123'}
    example_dict['arguments']['C'] = {'value': '-9'}
    example_dict['failures'] = []
    example_dict['failures'].append({'code': 'C', 'details': 'D'})
    example_dict['serialNumbers'] = {}
    example_dict['serialNumbers']['A'] = 'B'
    example_dict['parameters'] = {}
    example_dict['parameters']['A'] = {'description': 'D'}
    example_dict['parameters']['B'] = {'description': 'D', 'data': [
        {'numericValue': 987, 'status': 'PASS'},
        {'numericValue': 7.8, 'status': 'FAIL'}]}
    _unused_valid_event = testlog.EventBase.FromDict(example_dict)
    with self.assertRaises(schema.SchemaException):
      example_dict['arguments']['D'] = {}
      _unused_invalid_event = testlog.EventBase.FromDict(example_dict)


def SimulatedTestInAnotherProcess():
  # Only executed when we have environment variable TESTLOG
  if testlog.TESTLOG_ENV_VARIABLE_NAME not in os.environ:
    return

  # Initialize Testlog -- only needed because we don't have a harness
  # doing it for us.
  testlog.Testlog()

  logging.info('SUBPROCESS')
  # Snippet for attachment
  tmp_dir = tempfile.mkdtemp()
  def CreateTextFile():
    TEST_STR = 'I\'m just a little bit caught in the middle'
    TEST_FILENAME = 'TextFile.txt'
    path = os.path.join(tmp_dir, TEST_FILENAME)
    with open(path, 'w') as fd:
      fd.write(TEST_STR)
    return path

  # Additional steps that because multiprocessing.Process doesn't provide
  # an argument to set the env like subprocess.Popen.
  testlog.LogParam(name='NAME', value=1)

  # Wait the thread update the session json file.
  time.sleep(0.5)
  testlog.FlushEvent()

  testlog.UpdateParam('NAME', description='DESCRIPTION')

  # Move a file normally.
  file_to_attach = CreateTextFile()
  testlog.AttachFile(
      path=os.path.realpath(file_to_attach),
      name='FILE',
      mime_type='text/plain')

  # Clean up the tmp directory
  shutil.rmtree(tmp_dir)
  if testlog.TESTLOG_ENV_VARIABLE_NAME in os.environ:
    testlog.GetGlobalTestlog().Close()


class TestlogE2ETest(TestlogTestBase):

  def testE2E(self):
    IN_TAG = '$IN$'
    OUT_TAG = '$OUT$'
    # Assuming we are the harness.
    my_uuid = time_utils.TimedUUID()
    testlog.Testlog(log_root=self.state_dir, uuid=my_uuid)
    # Simulate the logging of goofy framework start-up.
    testlog.Log(testlog.StationInit({
        'count': 10,
        'success': True}))

    # Prepare for another test session.
    session_json_path = self._SimulateSubSession()
    env_additions = copy.deepcopy(os.environ)
    # Go with env_additions['TESTLOG']
    logging.info(IN_TAG)
    p = subprocess.Popen(
        ['python', os.path.abspath(__file__),
         'SimulatedTestInAnotherProcess'],
        env=env_additions)
    p.wait()
    logging.info(OUT_TAG)
    session_json = json.loads(open(session_json_path).read())
    # Collect the session log
    testlog.LogFinalTestRun(session_json_path)
    primary_json = file_utils.ReadLines(
        os.path.join(self.state_dir, 'testlog.json'))
    logging.info('Load back session JSON:\n%s\n', pprint.pformat(session_json))
    logging.info('Load back primary JSON:\n%s\n', ''.join(primary_json))

    expected_events = [
        {'type': 'station.message', 'seq': 0,
         'functionName': 'CaptureLogging', 'logLevel': 'INFO'},
        {'type': 'station.init', 'seq': 1, 'count': 10, 'success': True},
        {'type': 'station.message', 'seq': 2,
         'functionName': '_GetStationDeviceID', 'logLevel': u'WARNING'},
        {'type': 'station.message', 'seq': 3,
         'functionName': '_GetInstallationID', 'logLevel': 'INFO'},
        {'type': 'station.message', 'seq': 4,
         'functionName': 'testE2E', 'logLevel': 'INFO', 'message': '$IN$'},
        # Now that we are entering the subprocess, we should expect to see
        # testRunId == self.session_uuid.
        {'type': 'station.message', 'seq': 5,
         'functionName': 'CaptureLogging',
         'logLevel': 'INFO', 'testRunId': self.session_uuid},
        {'type': 'station.message', 'seq': 6,
         'functionName': 'SimulatedTestInAnotherProcess',
         'logLevel': 'INFO', 'testRunId': self.session_uuid},
        # Missing seq=7, 9, 10 because they are not sent to primary JSON.
        # This event is created by FlushEvent.
        {'type': 'station.test_run', 'seq': 8, 'testType': 'TestlogDemo',
         'testName': 'TestlogDemo.Test', 'testRunId': self.session_uuid,
         'parameters': {
             'NAME': {'data': [{'numericValue': 1}],
                      'type': 'measurement'}},
         'serialNumbers': {'serial_number': 'TestlogDemo'}},
        {'type': 'station.message',
         'functionName': 'testE2E', 'logLevel': 'INFO', 'message': '$OUT$'},
        # Don't check attachments since the filename is not deterministic.
        {'type': 'station.test_run', 'testType': 'TestlogDemo',
         'testName': 'TestlogDemo.Test', 'testRunId': self.session_uuid,
         'parameters': {
             'NAME': {'data': [{'numericValue': 1}],
                      'type': 'measurement',
                      'description': 'DESCRIPTION'}},
         'serialNumbers': {'serial_number': 'TestlogDemo'}}
    ]
    for i, json_string in enumerate(primary_json):
      dct = json.loads(json_string)
      self.assertDictContainsSubset(expected_events[i], dct)

  def testDisallowReenterLog(self):
    # FileLock records a DEBUG message after getting the file lock.
    logging.getLogger().setLevel(logging.DEBUG)
    # Assuming we are the harness.
    my_uuid = time_utils.TimedUUID()
    testlog.Testlog(log_root=self.state_dir, uuid=my_uuid)
    testlog.Log(testlog.StationInit({'count': 1, 'success': True}))
    logging.getLogger().setLevel(logging.INFO)


if __name__ == '__main__':
  logging.basicConfig(
      format=('[%(levelname)s] '
              ' %(threadName)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=logging.INFO,
      datefmt='%Y-%m-%d %H:%M:%S')
  unittest.main()
