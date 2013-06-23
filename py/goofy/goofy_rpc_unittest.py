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
import unittest2

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import goofy_rpc
from cros.factory.test import factory
from cros.factory.test import utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import test_utils

@contextmanager
def ReplaceAttribute(obj, name, value):
  old_value = getattr(obj, name)
  setattr(obj, name, value)
  try:
    yield
  finally:
    setattr(obj, name, old_value)


class GoofyRPCTest(unittest2.TestCase):
  def setUp(self):
    self.mox = mox.Mox()
    self.goofy_rpc = goofy_rpc.GoofyRPC(None)

    self.mox.StubOutWithMock(utils, 'var_log_messages_before_reboot')

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testGetVarLogMessages(self):
    with tempfile.NamedTemporaryFile(bufsize=0) as f:
      self.mox.stubs.Set(goofy_rpc, 'VAR_LOG_MESSAGES', f.name)
      data = ("Captain's log.\xFF\n"  # \xFF = invalid UTF-8
              "We are in pursuit of a starship of Ferengi design.\n")
      f.write(('X' * 100) + '\n' + data)
      # Use max_length=len(data) + 5 so that we'll end up reading
      # (and discarding) the last 5 bytes of garbage X's.
      self.assertEquals(
          u"<truncated 101 bytes>\n"
          u"Captain's log.\ufffd\n"
          u"We are in pursuit of a starship of Ferengi design.\n",
          self.goofy_rpc.GetVarLogMessages(max_length=(len(data) + 5)))

  def testGetVarLogMessagesBeforeReboot(self):
    utils.var_log_messages_before_reboot(lines=2, max_length=100).AndReturn(
        ['foo\xFF','bar'])
    self.mox.ReplayAll()
    self.assertEquals(u'foo\ufffd\nbar\n',
                      self.goofy_rpc.GetVarLogMessagesBeforeReboot(2, 100))

  def testGetVarLogMessagesBeforeRebootEmpty(self):
    utils.var_log_messages_before_reboot(lines=2, max_length=100).AndReturn([])
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

  def testTestLists(self):
    with file_utils.TempDirectory() as tmp:
      for name, contents in (
          ('not_a_test_list', 'ignored'),
          ('test_list', 'TEST_LIST_NAME = "Main test list"'),
          ('test_list.hello', '\n\nTEST_LIST_NAME = u"世界你好"\n\n'),
          ('test_list.unnamed', ''),
          ('test_list.ignored~', ''),  # ignored (temp file)
          ('test_list.generic', ''),   # ignored (overridden by test_list)
          ):
        open(os.path.join(tmp, name), 'w').write(contents)

      # Create a fake "options" object containing the active test list.
      options = type('FakeOptions', (),
                     dict(test_list=os.path.join(tmp, 'test_list.hello')))
      self.goofy_rpc.goofy = type('FakeGoofy', (),
                                  dict(options=options))

      with test_utils.StubOutAttributes(
          factory,
          TEST_LISTS_PATH=tmp,
          ACTIVE_TEST_LIST_SYMLINK=os.path.join(tmp, 'active')):
        self.assertEquals(
            [dict(enabled=False, id='', name='Main test list'),
             dict(enabled=False, id='unnamed', name='unnamed'),
             dict(enabled=True, id='hello', name='世界你好')],
            self.goofy_rpc.GetTestLists())

        for expected_link_target, test_list_id in (
            ('test_list', ''),
            ('test_list.hello', 'hello'),
            ('test_list.unnamed', 'unnamed')):
          self.assertRaisesRegexp(
              goofy_rpc.GoofyRPCException, 'manually restart Goofy',
              self.goofy_rpc.SwitchTestList, test_list_id)
          self.assertEquals(expected_link_target,
              os.readlink(factory.ACTIVE_TEST_LIST_SYMLINK))

        self.assertRaisesRegexp(
            goofy_rpc.GoofyRPCException, 'does not exist',
            self.goofy_rpc.SwitchTestList, 'nonexistent')


if __name__ == '__main__':
  unittest2.main()
