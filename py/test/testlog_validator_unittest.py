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
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import testlog
from cros.factory.test import testlog_goofy
from cros.factory.test import testlog_utils
from cros.factory.test import testlog_validator
from cros.factory.utils import time_utils

class TestlogValidatorTest(unittest.TestCase):
  class TestEvent(testlog.EventBase):
    """A derived class from Event that can be initialized."""
    FIELDS = {
        'Long':    (True, testlog_validator.Validator.Long),
        'Float':   (True, testlog_validator.Validator.Float),
        'String':  (True, testlog_validator.Validator.String),
        'Boolean': (True, testlog_validator.Validator.Boolean),
        'Dict':    (True, testlog_validator.Validator.Dict),
        'List':    (True, testlog_validator.Validator.List),
        'Time':    (True, testlog_validator.Validator.Time),
    }
    @classmethod
    def GetEventType(cls):
      return 'unittest.Event'

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

  def testFloatValidator(self):
    event = self.TestEvent()
    with self.assertRaises(ValueError):
      event['Float'] = '66'
    with self.assertRaises(ValueError):
      event['Float'] = 'aa'
    event['Float'] = 33.33
    self.assertAlmostEqual(event['Float'], 33.33)

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
    event2 = testlog.EventBase.FromJSON(event.ToJSON())
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


class StationTestRunValidatorTest(unittest.TestCase):
  """Validators primarily serve for StationTestRun."""
  def setUp(self):
    self.state_dir = testlog_goofy.LOG_ROOT
    self.tmp_dir = tempfile.mkdtemp()
    # Reset testlog if any
    # pylint: disable=W0212
    if testlog._global_testlog:
      testlog._global_testlog.Close()

  def tearDown(self):
    shutil.rmtree(self.state_dir)
    shutil.rmtree(self.tmp_dir)

  def testAttachmentValidator(self):
    # Prepare the attachments_folder by initializing testlog as a sub session
    os.environ[testlog.TESTLOG_ENV_VARIABLE_NAME] = testlog.InitSubSession(
        log_root=self.state_dir,
        station_test_run=testlog.StationTestRun(),
        uuid=time_utils.TimedUUID())

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


if __name__ == '__main__':
  logging.basicConfig(
      format=('[%(levelname)s] '
              ' %(threadName)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=logging.INFO,
      datefmt='%Y-%m-%d %H:%M:%S')
  unittest.main()
