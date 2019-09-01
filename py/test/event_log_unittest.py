#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for event_log.py."""


import collections
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import unittest
import uuid

import mock
import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.test import event_log
from cros.factory.test import session
from cros.factory.utils import file_utils

from cros.factory.external import dbus

UUID_RE = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-'
                     '[a-f0-9]{4}-[a-f0-9]{12}$')


_TestNamedTuple = collections.namedtuple('_TestNamedTuple', ['a', 'b', 'c'])


def Reset():
  # Deletes state files and resets global variables.
  event_log.device_id = event_log.reimage_id = None
  shutil.rmtree(event_log.EVENT_LOG_DIR, ignore_errors=True)
  for f in [session.DEVICE_ID_PATH, event_log.SEQUENCE_PATH,
            event_log.BOOT_SEQUENCE_PATH, event_log.EVENTS_PATH]:
    file_utils.TryUnlink(f)


class BasicTest(unittest.TestCase):
  """Tests basic elements in event_log.py."""

  def testEventNameRE(self):
    for i in ('a', '_', 'azAZ09_', 'a0'):
      self.assertTrue(event_log.EVENT_NAME_RE.match(i))

    for i in ('', 'a.', '0', '0a'):
      self.assertFalse(event_log.EVENT_NAME_RE.match(i))


class GlobalSeqTest(unittest.TestCase):
  """Unittests for GlobalSeq."""

  def setUp(self):
    Reset()
    self.tmp = tempfile.mkdtemp(prefix='GlobalSeqTest.')

  def tearDown(self):
    shutil.rmtree(self.tmp)

  def testBasic(self):
    seq = event_log.GlobalSeq()
    for i in range(3):
      self.assertEquals(i, seq.Next())
    del seq

    # Try again with a new sequence file
    seq = event_log.GlobalSeq()
    for i in range(3, 6):
      self.assertEquals(i, seq.Next())
    del seq

  def testYamlDump(self):
    class OtherType(object):
      """A generic class."""

      def __init__(self, attr_foo):
        self.attr_foo = attr_foo

    dump = lambda x: event_log.YamlDump(x).strip()
    # FloatDigit type
    self.assertEqual('\n'.join(['0.1235', '...']),
                     dump(event_log.FloatDigit(0.12345, 4)))
    # A subclass of a dict
    self.assertEqual('\n'.join(['bar: 1', 'foo: 3']),
                     dump(collections.OrderedDict([('bar', 1), ('foo', 3)])))
    # A subclass of a list
    self.assertEqual('\n'.join(['- comp_foo', '- value_foo', '- null']),
                     dump(_TestNamedTuple('comp_foo', 'value_foo', None)))
    # Tuple type
    self.assertEqual('\n'.join(['- v1', '- v2', '- v3']),
                     dump(('v1', 'v2', 'v3')))
    # A subclass of an unicode, treating as a str
    self.assertEqual('\n'.join(['a dbus string', '...']),
                     dump(dbus.String('a dbus string')))
    # A general object
    self.assertEqual('\n'.join(['attr_foo: Foo']),
                     dump(OtherType('Foo')))
    # An object without attribute
    self.assertEqual('{}', dump(self.testYamlDump))

  def testMissingSequenceFile(self):
    # Generate a few sequence numbers.
    seq = event_log.GlobalSeq()
    self.assertEquals(0, seq.Next())
    self.assertEquals(1, seq.Next())
    # Log an event (preamble will have sequence number 2; main
    # event will have 3).
    event_log.EventLog('test:foo').Log('bar')
    with open(event_log.EVENTS_PATH) as f:
      assert 'SEQ: 3\n' in f.readlines()

    # Delete the sequence file to simulate corruption.
    os.unlink(event_log.SEQUENCE_PATH)
    # Sequence file should be re-created, starting with 4 plus
    # SEQ_INCREMENT_ON_BOOT.
    self.assertEquals(4 + event_log.SEQ_INCREMENT_ON_BOOT,
                      seq.Next())

    # Delete the sequence file and create a new GlobalSeq object to
    # simulate a reboot.  We'll do this a few times.
    for i in range(3):
      # Log an event to record the new sequence number for "reboot"
      event_log.EventLog('test:foo').Log('bar')

      del seq
      os.unlink(event_log.SEQUENCE_PATH)
      seq = event_log.GlobalSeq()
      # Sequence file should be re-created, increasing by 2 for the logged
      # event, and SEQ_INCREMENT_ON_BOOT for the reboot.
      self.assertEquals(7 + i * 3 + (i + 2) * event_log.SEQ_INCREMENT_ON_BOOT,
                        seq.Next())

  def _testThreads(self, after_read=lambda: True):
    """Tests atomicity by doing operations in 10 threads for 1 sec.

    Args:
      after_read: See GlobalSeq._after_read.
    """
    values = []
    start_time = time.time()
    end_time = start_time + 1

    def target():
      with mock.patch('os.fsync'):
        seq = event_log.GlobalSeq(_after_read=after_read)
        while time.time() < end_time:
          values.append(seq.Next())

    threads = [threading.Thread(target=target) for _ in xrange(10)]
    for t in threads:
      t.start()
    for t in threads:
      t.join()

    # After we sort, should be numbers [0, len(values)).
    values.sort()
    self.assertEquals(range(len(values)), values)
    return values

  def testThreadsWithSleep(self):
    values = self._testThreads(after_read=lambda: time.sleep(.05))
    # There should be about 20 to 30 values (1 every 50 ms for 1 s, plus
    # a number less than the number of threads).
    # Significantly more or less than that and something went wrong.
    self.assertGreater(len(values), 10)
    self.assertLess(len(values), 30)

  def testThreadsWithoutSleep(self):
    values = self._testThreads()
    # There should be lots of values (I get over 35000 on my desktop); we'll
    # just make sure there are >1000.
    self.assertGreater(len(values), 1000)


class EventLogTest(unittest.TestCase):
  """Unittests for EventLog."""

  def setUp(self):
    Reset()
    self.tmp = tempfile.mkdtemp()

  def tearDown(self):
    shutil.rmtree(self.tmp)

  def testGetBootId(self):
    assert UUID_RE.match(event_log.GetBootId())


  def testGetReimageId(self):
    reimage_id = event_log.GetReimageId()
    assert UUID_RE.match(reimage_id), reimage_id

  def testSuppress(self):
    for suppress in [False, True]:
      Reset()
      log = event_log.EventLog('test:test', suppress=suppress)
      log.Log('test')
      self.assertEquals(suppress, not os.path.exists(event_log.EVENTS_PATH))

  def testEventLogDefer(self):
    self._testEventLog(True)

  def testEventLogNoDefer(self):
    self._testEventLog(False)

  def _testEventLog(self, defer):
    log = event_log.EventLog('test:test', defer=defer)
    self.assertEqual(os.path.exists(event_log.EVENTS_PATH), not defer)

    event0 = dict(a='A',
                  b=1,
                  c=[1, 2],
                  d={'D1': 3, 'D2': 4},
                  e=['E1', {'E2': 'E3'}],
                  f=True,
                  g=u'[[[囧]]]'.encode('utf-8'),
                  h=u'[[[囧]]]')
    log.Log('event0', **event0)

    # Open and close another logger as well
    event2 = dict(foo='bar')
    log2 = event_log.EventLog('test:test2', defer=defer)
    log2.Log('event2', **event2)
    log2.Close()

    log.Log('event1')
    log.Close()

    try:
      log.Log('should-fail')
      self.fail('Expected exception')
    except Exception:
      pass

    log_data = list(yaml.load_all(open(event_log.EVENTS_PATH, 'r')))
    self.assertEqual(6, len(log_data))
    # The last one should be empty; remove it
    self.assertIsNone(None, log_data[-1])
    log_data = log_data[0:-1]

    for i in log_data:
      # Check and remove times, to make everything else easier to compare
      assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$',
                      i['TIME']), i['TIME']
      del i['TIME']

    self.assertEqual(
        ['EVENT', 'LOG_ID', 'PREFIX', 'SEQ',
         'boot_id', 'boot_sequence', 'device_id', 'reimage_id',
         'toolkit_version'],
        sorted(log_data[0].keys()))
    self.assertEqual('preamble', log_data[0]['EVENT'])
    self.assertEqual('test:test', log_data[0]['PREFIX'])
    self.assertEqual(0, log_data[0]['SEQ'])
    self.assertEqual(event_log.GetBootId(), log_data[0]['boot_id'])
    self.assertEqual(-1, log_data[0]['boot_sequence'])
    self.assertEqual(session.GetDeviceID(), log_data[0]['device_id'])
    self.assertEqual(event_log.GetReimageId(), log_data[0]['reimage_id'])
    log_id = log_data[0]['LOG_ID']
    uuid.UUID(log_id)  # Make sure UUID is well-formed

    # Check all the events
    event0.update(
        dict(EVENT='event0',
             SEQ=1,
             LOG_ID=log_id,
             PREFIX='test:test'))
    # Yaml loader converts non-ASCII strings to unicode.
    event0['g'] = event0['h']
    self.assertEqual(event0, log_data[1])
    self.assertEqual(
        dict(EVENT='preamble',
             LOG_ID=log2.log_id,
             PREFIX='test:test2',
             SEQ=2,
             boot_id=event_log.GetBootId(),
             boot_sequence=-1,
             device_id=session.GetDeviceID(),
             toolkit_version=None,
             reimage_id=event_log.GetReimageId()),
        log_data[2])
    # Check the preamble and event from the second logger
    self.assertEqual(
        dict(EVENT='event2',
             LOG_ID=log2.log_id,
             PREFIX='test:test2',
             SEQ=3,
             foo='bar'),
        log_data[3])
    self.assertEqual(
        dict(EVENT='event1',
             SEQ=4,
             LOG_ID=log_id,
             PREFIX='test:test'),
        log_data[4])

  def testDeferWithoutEvents(self):
    log = event_log.EventLog('test:test', defer=True)
    log.Close()
    self.assertFalse(os.path.exists(event_log.EVENTS_PATH))


class GlobalEventLogTest(unittest.TestCase):
  """Unittests for GetGlobalLogger."""

  def setUp(self):
    # reset the global event logger
    event_log._global_event_logger = None  # pylint: disable=protected-access
    # pylint: disable=protected-access
    event_log._default_event_logger_prefix = None

    if 'CROS_FACTORY_TEST_PATH' in os.environ:
      del os.environ['CROS_FACTORY_TEST_PATH']
    if 'CROS_FACTORY_TEST_INVOCATION' in os.environ:
      del os.environ['CROS_FACTORY_TEST_INVOCATION']

  def testGlobalInstanceNoEnv(self):
    self.assertRaises(ValueError, event_log.GetGlobalLogger)

  def testGlobalInstancePrefix(self):
    event_log.SetGlobalLoggerDefaultPrefix('bar')
    log = event_log.GetGlobalLogger()
    self.assertEqual('bar', log.prefix)
    self.assertTrue(log.log_id)

  def testInvalidDefaultPrefix(self):
    self.assertRaises(ValueError,
                      event_log.SetGlobalLoggerDefaultPrefix, '---')

  def testDefaultPrefix(self):
    os.environ['CROS_FACTORY_TEST_PATH'] = 'FooTest'
    event_log.SetGlobalLoggerDefaultPrefix('bar')

    log = event_log.GetGlobalLogger()
    self.assertEqual('bar', log.prefix)
    self.assertTrue(log.log_id)

    self.assertRaises(event_log.EventLogException,
                      event_log.SetGlobalLoggerDefaultPrefix, 'bar2')

  def testGlobalInstanceWithEnv(self):
    stub_uuid = 'bfa88756-ef2b-4e58-a4a2-eda1408bc93f'
    os.environ['CROS_FACTORY_TEST_PATH'] = 'FooTest'
    os.environ['CROS_FACTORY_TEST_INVOCATION'] = stub_uuid

    log = event_log.GetGlobalLogger()
    self.assertEqual('FooTest', log.prefix)
    self.assertEqual(stub_uuid, log.log_id)

  def testSingleton(self):
    os.environ['CROS_FACTORY_TEST_PATH'] = 'FooTest'
    # pylint: disable=protected-access
    self.assertEquals(None, event_log._global_event_logger)
    log1 = event_log.GetGlobalLogger()
    log2 = event_log.GetGlobalLogger()
    self.assertTrue(log1 is log2)

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
