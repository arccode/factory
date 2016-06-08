#!/usr/bin/python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import datetime
import logging
import os
import shutil
import subprocess
import sys
import unittest
from uuid import uuid4

import factory_common  # pylint: disable=W0611
from cros.factory.test import testlog
from cros.factory.test import testlog_goofy
from cros.factory.utils import file_utils

SAMPLE_DATETIME = datetime.datetime(1989, 8, 8, 8, 8, 8, 888888)
SAMPLE_DATETIME_STRING = '1989-08-08T08:08:08.888Z'
SAMPLE_DATETIME_ROUNDED_MIL = datetime.datetime(1989, 8, 8, 8, 8, 8, 888000)
SAMPLE_DATETIME_ROUNDED_SEC = datetime.datetime(1989, 8, 8, 8, 8, 8, 000000)


class TestlogTest(unittest.TestCase):

  def testJSONTime(self):
    """Tests conversion to and from JSON date format.

    Microseconds should be stripped to precision of 3 decimal points."""
    # pylint: disable=W0212
    output = testlog._FromJSONDateTime(
        testlog._ToJSONDateTime(SAMPLE_DATETIME))
    self.assertEquals(output, SAMPLE_DATETIME_ROUNDED_MIL)

    output = testlog._FromJSONDateTime(
        testlog._ToJSONDateTime(SAMPLE_DATETIME_ROUNDED_SEC))

  def testJSONHandlerDateTime(self):
    obj = SAMPLE_DATETIME
    # pylint: disable=W0212
    output = testlog._JSONHandler(obj)
    self.assertEquals(output, SAMPLE_DATETIME_STRING)
    self.assertEquals(output, testlog._ToJSONDateTime(obj))

  def testJSONHandlerDate(self):
    obj = datetime.date(1989, 8, 8)
    # pylint: disable=W0212
    output = testlog._JSONHandler(obj)
    self.assertEquals(output, '1989-08-08')

  def testJSONHandlerTime(self):
    obj = datetime.time(22, 10, 10)
    # pylint: disable=W0212
    output = testlog._JSONHandler(obj)
    self.assertEquals(output, '22:10')

  def testJSONHandlerExceptionAndTraceback(self):
    try:
      1 / 0
    except Exception:
      _, ex, tb = sys.exc_info()
      # pylint: disable=W0212
      output = testlog._JSONHandler(tb)
      self.assertTrue('1 / 0' in output)
      output = testlog._JSONHandler(ex)
      self.assertTrue(output.startswith('Exception: '))

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
    with self.assertRaisesRegexp(testlog.TestlogError, 'initialize directly'):
      testlog.EventBase()
    with self.assertRaisesRegexp(testlog.TestlogError, 'initialize directly'):
      testlog.Event()
    with self.assertRaisesRegexp(testlog.TestlogError, 'initialize directly'):
      testlog._StationBase()  # pylint: disable=W0212

  def testEventSerializeUnserialize(self):
    original = testlog.StationInit()
    output = testlog.Event.FromJSON(original.ToJSON())
    self.assertEquals(output, original)

  def testNewEventTime(self):
    event = testlog.StationInit({'time': SAMPLE_DATETIME})
    self.assertEquals(event['time'], SAMPLE_DATETIME_ROUNDED_MIL)
    event = testlog.StationInit({'time': SAMPLE_DATETIME_ROUNDED_MIL})
    self.assertEquals(event['time'], SAMPLE_DATETIME_ROUNDED_MIL)
    event = testlog.StationInit({'time': SAMPLE_DATETIME_STRING})
    self.assertEquals(event['time'], SAMPLE_DATETIME_ROUNDED_MIL)
    with self.assertRaises(testlog.TestlogError):
      event = testlog.StationInit({'time': None})

  def testPopulateReturnsSelf(self):
    event = testlog.StationInit()
    self.assertEquals(event.Populate({}), event)

  def testInvalidStatusTestRun(self):
    with self.assertRaises(testlog.TestlogError):
      testlog.StationTestRun({'status': True})


class TestlogE2ETest(unittest.TestCase):
  @staticmethod
  def _reset():
    """Deletes state files and resets global variables."""
    # pylint: disable=W0212
    testlog_goofy._device_id = testlog_goofy._reimage_id = None
    if testlog._global_testlog:
      testlog._global_testlog.Close()
    state_dir = testlog_goofy.LOG_ROOT
    for f in [testlog_goofy.DEVICE_ID_PATH,
              testlog_goofy.REIMAGE_ID_PATH,
              testlog_goofy.INIT_COUNT_PATH,
              testlog._SEQUENCE_PATH,
              os.path.join(state_dir, testlog._DEFAULT_PRIMARY_JSON_FILE)]:

      file_utils.TryUnlink(f)
    for d in [os.path.join(state_dir, testlog._DEFAULT_SESSION_FOLDER),
              os.path.join(state_dir, testlog._DEFAULT_ATTACHMENTS_FOLDER)]:
      shutil.rmtree(d, ignore_errors=True)
    if testlog.TESTLOG_ENV_VARIABLE_NAME in os.environ:
      del os.environ[testlog.TESTLOG_ENV_VARIABLE_NAME]

  def tearDown(self):
    # pylint: disable=W0212
    if testlog._global_testlog:
      testlog._global_testlog.Close()

  def testSimulatedTestInAnotherProcess(self):
    # Only executed when we have environment variable TESTLOG
    if testlog.TESTLOG_ENV_VARIABLE_NAME not in os.environ:
      return

    logging.info("Running Oataku pytest")
    # Additional steps that because multiprocessing.Process doesn't provide
    # an argument to set the env like subprocess.Popen.
    testlog.LogParam(name='Oataku', value=22000,
                     description='Obtained from http://i.imgur.com/hK0X8.jpg')

  def testE2E(self):
    TestlogE2ETest._reset()
    state_dir = testlog_goofy.LOG_ROOT
    # Assuming we are the harness.
    my_uuid = uuid4()
    testlog.Testlog(log_root=state_dir, uuid=my_uuid)
    logging.info("# Simulate the logging of goofy framework start-up.")
    testlog.Log(testlog.StationInit({
        'count': testlog_goofy.GetInitCount(),
        'success': True}))

    logging.info("# Prepare for another test session.")
    session_uuid = uuid4()
    session_test_run = testlog.StationTestRun()
    session_test_run.Populate({
        'stationDeviceId': testlog_goofy.GetDeviceID(),
        'stationReimageId': testlog_goofy.GetReimageID(),
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
    env_additions.update({"TESTLOG": session_json_path})
    logging.info("# Go with %s", env_additions["TESTLOG"])
    p = subprocess.Popen(
        ['python', os.path.abspath(__file__),
         "TestlogE2ETest.testSimulatedTestInAnotherProcess"],
        env=env_additions)
    p.wait()
    # Collect the session log
    testlog.Collect(session_json_path)


if __name__ == '__main__':
  logging.basicConfig(
      format=('[%(levelname)s] '
              ' %(threadName)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=logging.INFO,
      datefmt='%Y-%m-%d %H:%M:%S')
  unittest.main()
