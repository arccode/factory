#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from contextlib import contextmanager
import mox
import tempfile
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import goofy_rpc
from cros.factory.test import utils
from cros.factory.utils import process_utils

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


if __name__ == '__main__':
  unittest.main()
