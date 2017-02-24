#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from contextlib import contextmanager
import mox
import os
import tempfile
import time
import unittest
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import goofy
from cros.factory.goofy import goofy_rpc
from cros.factory.test.env import paths
from cros.factory.test import factory
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils
from cros.factory.device import board
from cros.factory.device import link
from cros.factory.device import status


@contextmanager
def ReplaceAttribute(obj, name, value):
  old_value = getattr(obj, name)
  setattr(obj, name, value)
  try:
    yield
  finally:
    setattr(obj, name, old_value)


class GoofyRPCTest(unittest.TestCase):

  def setUp(self):
    self.mox = mox.Mox()
    self.goofy = self.mox.CreateMock(goofy)
    self.goofy_rpc = goofy_rpc.GoofyRPC(self.goofy)

    self.mox.StubOutWithMock(sys_utils, 'GetVarLogMessagesBeforeReboot')

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testGetVarLogMessages(self):
    with tempfile.NamedTemporaryFile(bufsize=0) as f:
      self.mox.stubs.Set(goofy_rpc, 'VAR_LOG_MESSAGES', f.name)
      data = ("Captain's log.\xFF\n"  # \xFF = invalid UTF-8
              'We are in pursuit of a starship of Ferengi design.\n')
      f.write(('X' * 100) + '\n' + data)
      # Use max_length=len(data) + 5 so that we'll end up reading
      # (and discarding) the last 5 bytes of garbage X's.
      self.assertEquals(
          u'<truncated 101 bytes>\n'
          u"Captain's log.\ufffd\n"
          u'We are in pursuit of a starship of Ferengi design.\n',
          self.goofy_rpc.GetVarLogMessages(max_length=(len(data) + 5)))

  def testGetVarLogMessagesBeforeReboot(self):
    sys_utils.GetVarLogMessagesBeforeReboot(lines=2, max_length=100).AndReturn(
        ['foo\xFF', 'bar'])
    self.mox.ReplayAll()
    self.assertEquals(u'foo\ufffd\nbar\n',
                      self.goofy_rpc.GetVarLogMessagesBeforeReboot(2, 100))

  def testGetVarLogMessagesBeforeRebootEmpty(self):
    sys_utils.GetVarLogMessagesBeforeReboot(lines=2,
                                            max_length=100).AndReturn([])
    self.mox.ReplayAll()
    self.assertEquals(None,
                      self.goofy_rpc.GetVarLogMessagesBeforeReboot(2, 100))

  def testGetDmesg(self):
    self.mox.StubOutWithMock(process_utils, 'Spawn')
    self.mox.StubOutWithMock(self.goofy_rpc, '_ReadUptime')
    self.mox.StubOutWithMock(time, 'time')
    process_utils.Spawn(['dmesg'], check_call=True, read_stdout=True).AndReturn(
        type('', (object,), dict(stdout_data=('[ 123.0] A\n'
                                              '[2345.0] B\n'))))
    self.goofy_rpc._ReadUptime().AndReturn('3000.0')  # pylint: disable=W0212
    time.time().AndReturn(1343806777.0)
    self.mox.ReplayAll()
    self.assertEquals('2012-08-01T06:51:40.000Z [ 123.0] A\n'
                      '2012-08-01T07:28:42.000Z [2345.0] B\n',
                      self.goofy_rpc.GetDmesg())

  def testGetTestList(self):
    test_list = "data"
    self.goofy.test_list = self.mox.CreateMock(factory.FactoryTestList)
    self.goofy.test_list.to_struct().AndReturn(test_list)

    self.mox.ReplayAll()

    self.assertEqual(
        test_list,
        self.goofy_rpc.GetTestList())

  def testGetTestHistory(self):
    data = {'A': 1, 'b': 'abc'}
    test_path = 'a.b.c'
    invocations = ['123', '456']
    expected = []

    for invocation in invocations:
      path = os.path.join(paths.GetTestDataRoot(),
                          test_path + '-%s' % invocation,
                          'metadata')
      file_utils.TryMakeDirs(os.path.dirname(path))
      with open(path, 'w') as f:
        data['init_time'] = invocation
        yaml.dump(data, f, default_flow_style=False)
      expected.append(data.copy())

    self.assertEqual(expected, self.goofy_rpc.GetTestHistory(test_path))

  def testGetTestHistoryEntry(self):
    path = 'a.b.c'
    invocation = '123'

    log = 'This is the test log'
    data = {'A': 1, 'b': 'abc'}

    test_dir = os.path.join(paths.GetTestDataRoot(),
                            '%s-%s' % (path, invocation))

    file_utils.TryMakeDirs(test_dir)
    log_file = os.path.join(test_dir, 'log')
    metadata_file = os.path.join(test_dir, 'metadata')

    with open(log_file, 'w') as f:
      f.write(log)

    with open(metadata_file, 'w') as f:
      yaml.dump(data, f)

    self.assertEqual(
        {'metadata': data,
         'log': log},
        self.goofy_rpc.GetTestHistoryEntry(path, invocation))

  def testGetSystemStatus(self):
    class Data(object):
      def __init__(self):
        self.data = '123'

    # pylint: disable=protected-access
    self.goofy.dut = self.mox.CreateMock(board.DeviceBoard)
    self.goofy.dut.link = self.mox.CreateMock(link.DeviceLink)
    self.goofy.dut.status = self.mox.CreateMock(status.SystemStatus)

    snapshot = Data()
    self.goofy.dut.link.IsLocal().AndReturn(True)
    self.goofy.dut.status.Snapshot().AndReturn(snapshot)
    self.mox.ReplayAll()
    self.assertTrue(snapshot.__dict__, self.goofy_rpc.GetSystemStatus())

    self.goofy.dut.link = self.mox.CreateMock(link.DeviceLink)
    self.goofy.dut.link.IsLocal().AndReturn(False)
    self.mox.ReplayAll()
    self.assertIsNone(self.goofy_rpc.GetSystemStatus())


if __name__ == '__main__':
  unittest.main()
