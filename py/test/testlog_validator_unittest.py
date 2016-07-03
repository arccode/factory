#!/usr/bin/python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import datetime
import logging
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import testlog
from cros.factory.test import testlog_utils
from cros.factory.test import testlog_validator

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


if __name__ == '__main__':
  logging.basicConfig(
      format=('[%(levelname)s] '
              ' %(threadName)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=logging.DEBUG,
      datefmt='%Y-%m-%d %H:%M:%S')
  unittest.main()
