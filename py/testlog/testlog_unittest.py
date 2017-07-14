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
import subprocess
import tempfile
import unittest

from testlog_pkg import testlog
from testlog_pkg import testlog_utils
from testlog_pkg.utils import file_utils
from testlog_pkg.utils import time_utils


SAMPLE_DATETIME = datetime.datetime(1989, 8, 8, 8, 8, 8, 888888)
SAMPLE_DATETIME_STRING = '1989-08-08T08:08:08.888Z'
SAMPLE_DATETIME_ROUNDED_MIL = datetime.datetime(1989, 8, 8, 8, 8, 8, 888000)


class TestlogTest(unittest.TestCase):

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


class TestlogEventTest(unittest.TestCase):

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
    event = testlog.StationInit({'time': SAMPLE_DATETIME})
    self.assertEquals(event['time'], SAMPLE_DATETIME_ROUNDED_MIL)
    event = testlog.StationInit({'time': SAMPLE_DATETIME_ROUNDED_MIL})
    self.assertEquals(event['time'], SAMPLE_DATETIME_ROUNDED_MIL)
    event = testlog.StationInit({'time': SAMPLE_DATETIME_STRING})
    self.assertEquals(event['time'], SAMPLE_DATETIME_ROUNDED_MIL)
    with self.assertRaises(ValueError):
      event = testlog.StationInit({'time': None})

  def testPopulateReturnsSelf(self):
    event = testlog.StationInit()
    self.assertIs(event.Populate({}), event)

  def testInvalidStatusTestRun(self):
    with self.assertRaises(ValueError):
      testlog.StationTestRun({'status': True})

  def testCheckMissingFields(self):
    event = testlog.StationInit()
    event['failureMessage'] = 'Missed fields'
    try:
      event.CheckMissingFields()
    except testlog_utils.TestlogError as e:
      self.assertEqual(repr(e), 'TestlogError("Missing fields: [\'count\', '
                       '\'success\', \'uuid\', \'apiVersion\', \'time\']",)')

  def testAddArgument(self):
    event = testlog.StationTestRun()
    event.AddArgument('K1', 'V1')
    event.AddArgument('K2', 2.2, 'D2')
    self.assertEquals(
        testlog.StationTestRun({
            'type': 'station.test_run',
            'arguments': {
                'K1': {'value': 'V1'},
                'K2': {'value': 2.2, 'description': 'D2'}}}),
        event)


class TestlogE2ETest(unittest.TestCase):
  @staticmethod
  def _reset():
    """Deletes state files and resets global variables."""
    # pylint: disable=protected-access
    if testlog._global_testlog:
      testlog._global_testlog.Close()
    file_utils.TryUnlink(testlog._SEQUENCE_PATH)
    if testlog.TESTLOG_ENV_VARIABLE_NAME in os.environ:
      del os.environ[testlog.TESTLOG_ENV_VARIABLE_NAME]

  def tearDown(self):
    # pylint: disable=protected-access
    if testlog._global_testlog:
      testlog._global_testlog.Close()

  def testSimulatedTestInAnotherProcess(self):
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
    testlog.LogParam(name='NAME', value=1,
                     description='DESCRIPTION')

    # Move a file normally.
    file_to_attach = CreateTextFile()
    testlog.AttachFile(
        path=os.path.realpath(file_to_attach),
        name='FILE',
        mime_type='text/plain')

    # Clean up the tmp directory
    shutil.rmtree(tmp_dir)

  def testE2E(self):
    def _GetDeviceID():
      logging.warning('WARNING')
      return 'ThisIsDeviceID'

    def _GetInstallationID():
      logging.info('INFO')
      return 'ThisIsInstallationID'

    IN_TAG = '$IN$'
    OUT_TAG = '$OUT$'
    TestlogE2ETest._reset()
    state_dir = tempfile.mkdtemp()
    # Assuming we are the harness.
    my_uuid = time_utils.TimedUUID()
    testlog.Testlog(log_root=state_dir, uuid=my_uuid)
    # Simulate the logging of goofy framework start-up.
    testlog.Log(testlog.StationInit({
        'count': 10,
        'success': True}))

    # Prepare for another test session.
    session_uuid = time_utils.TimedUUID()
    session_test_run = testlog.StationTestRun()
    session_test_run.Populate({
        'stationDeviceId': _GetDeviceID(),
        'stationInstallationId': _GetInstallationID(),
        'testRunId': session_uuid,
        'testName': 'TestlogDemo',
        'status': testlog.StationTestRun.STATUS.STARTING,
        'startTime': SAMPLE_DATETIME_STRING,
        })
    # Go
    session_json_path = testlog.InitSubSession(
        log_root=state_dir,
        station_test_run=session_test_run,
        uuid=session_uuid)
    env_additions = copy.deepcopy(os.environ)
    env_additions.update({'TESTLOG': session_json_path})
    # Go with env_additions['TESTLOG']
    logging.info(IN_TAG)
    p = subprocess.Popen(
        ['python', os.path.abspath(__file__),
         'TestlogE2ETest.testSimulatedTestInAnotherProcess'],
        env=env_additions)
    p.wait()
    logging.info(OUT_TAG)
    session_json = json.loads(open(session_json_path).read())
    # Collect the session log
    testlog.LogFinalTestRun(session_json_path)
    primary_json = open(os.path.join(state_dir, 'testlog.json')).readlines()
    logging.info('Load back session JSON:\n%s\n', pprint.pformat(session_json))
    logging.info('Load back primary JSON:\n%s\n', ''.join(primary_json))

    expected_events = [
        {'type': 'station.message', 'seq': 0,
         'functionName': 'CaptureLogging', 'logLevel': 'INFO'},
        {'type': 'station.init', 'seq': 1, 'count': 10, 'success': True},
        {'type': 'station.message', 'seq': 2,
         'functionName': '_GetDeviceID', 'logLevel': u'WARNING'},
        {'type': 'station.message', 'seq': 3,
         'functionName': '_GetInstallationID', 'logLevel': 'INFO'},
        {'type': 'station.message', 'seq': 4,
         'functionName': 'testE2E', 'logLevel': 'INFO', 'message': '$IN$'},
        # Now that we are entering the subprocess, we should expect to see
        # testRunId == session_uuid.
        {'type': 'station.message', 'seq': 5,
         'functionName': 'CaptureLogging',
         'logLevel': 'INFO', 'testRunId': session_uuid},
        {'type': 'station.message', 'seq': 6,
         'functionName': 'testSimulatedTestInAnotherProcess',
         'logLevel': 'INFO', 'testRunId': session_uuid},
        # Missing seq=7 and seq=8 because they are sent to primary JSON.
        {'type': 'station.message', 'seq': 9,
         'functionName': 'testE2E', 'logLevel': 'INFO', 'message': '$OUT$'},
        # Don't check attachments since the filename is not deterministic.
        {'type': 'station.test_run', 'seq': 10,
         'testName': 'TestlogDemo', 'testRunId': session_uuid,
         'parameters': {
             'NAME': {'numericValue': 1, 'description': 'DESCRIPTION'}}},
    ]
    for i, json_string in enumerate(primary_json):
      dct = json.loads(json_string)
      self.assertDictContainsSubset(expected_events[i], dct)

  def testDisallowReenterLog(self):
    # FileLock records a DEBUG message after getting the file lock.
    logging.getLogger().setLevel(logging.DEBUG)
    TestlogE2ETest._reset()
    state_dir = tempfile.mkdtemp()
    # Assuming we are the harness.
    my_uuid = time_utils.TimedUUID()
    testlog.Testlog(log_root=state_dir, uuid=my_uuid)
    testlog.Log(testlog.StationInit({}))
    logging.getLogger().setLevel(logging.INFO)


if __name__ == '__main__':
  logging.basicConfig(
      format=('[%(levelname)s] '
              ' %(threadName)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=logging.INFO,
      datefmt='%Y-%m-%d %H:%M:%S')
  unittest.main()
