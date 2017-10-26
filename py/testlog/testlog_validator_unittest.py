#!/usr/bin/python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import datetime
import logging
import unittest

from testlog_pkg import testlog
from testlog_pkg import testlog_utils
from testlog_pkg import testlog_validator
from testlog_pkg.utils import schema


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


if __name__ == '__main__':
  logging.basicConfig(
      format=('[%(levelname)s] '
              ' %(threadName)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=logging.INFO,
      datefmt='%Y-%m-%d %H:%M:%S')
  unittest.main()
