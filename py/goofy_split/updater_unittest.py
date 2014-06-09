#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest
import mox
import threading

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import updater
from cros.factory.test import factory
from cros.factory.test import shopfloor


class CheckForUpdateTest(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.UnsetStubs()

  def testMustUpdate(self):
    self.mox.StubOutWithMock(shopfloor, 'get_instance')
    self.mox.StubOutWithMock(factory, 'get_current_md5sum')
    fake_shopfloor = self.mox.CreateMockAnything()
    fake_shopfloor.use_umpire = False
    shopfloor.get_instance(detect=True, timeout=3).AndReturn(fake_shopfloor)
    fake_shopfloor.GetTestMd5sum().AndReturn('11111')
    factory.get_current_md5sum().AndReturn('00000')
    fake_shopfloor.NeedsUpdate('00000').AndReturn(True)
    self.mox.ReplayAll()
    self.assertEquals(updater.CheckForUpdate(3), ('11111', True))
    self.mox.VerifyAll()

  def testNotUpdate(self):
    self.mox.StubOutWithMock(shopfloor, 'get_instance')
    fake_shopfloor = self.mox.CreateMockAnything()
    fake_shopfloor.use_umpire = False
    shopfloor.get_instance(detect=True, timeout=3).AndReturn(fake_shopfloor)
    fake_shopfloor.GetTestMd5sum().AndReturn('11111')
    self.mox.StubOutWithMock(factory, 'get_current_md5sum')
    factory.get_current_md5sum().AndReturn('11111')
    fake_shopfloor.NeedsUpdate('11111').AndReturn(False)
    self.mox.ReplayAll()
    self.assertEquals(updater.CheckForUpdate(3), ('11111', False))
    self.mox.VerifyAll()


class CheckForUpdateAsyncTest(unittest.TestCase):
  '''Test CheckForUpdateAsync with mocked CheckForUpdate and other functions.'''
  def CallbackCalled(self, *unused_args, **unused_kwargs):
    '''Arguments of this function are dummy.'''
    self.event.set()

  def setUp(self):
    self.mox = mox.Mox()
    self.event = threading.Event()
    self.event.clear()

  def tearDown(self):
    self.mox.UnsetStubs()

  def _testUpdate(self, available):
    '''Provides basic testing flow for testMustUpdate and testNotUpdate.'''
    self.mox.StubOutWithMock(updater, 'CheckForUpdate')
    updater.CheckForUpdate(1).AndReturn(('11111', available))
    callback = self.mox.CreateMockAnything()
    callback(True, '11111', available).WithSideEffects(  # pylint: disable=E1102
        self.CallbackCalled)
    self.mox.ReplayAll()
    updater.CheckForUpdateAsync(callback, 1)

    # In the real use case, CheckForUpdate requires a timeout. However it has
    # already been stubbed out and will return immediately in this unittest.
    # If something is wrong in CheckForUpdateAsync, we will wait for
    # at most 1 second and verify its correctness.

    self.event.wait(1)
    self.mox.VerifyAll()

  def testMustUpdate(self):
    self._testUpdate(True)

  def testNotUpdate(self):
    self._testUpdate(False)

  def testCanNotReach(self):
    self.mox.StubOutWithMock(updater, 'CheckForUpdate')
    updater.CheckForUpdate(1).AndRaise(
        Exception('Can not contact shopfloorserver'))
    callback = self.mox.CreateMockAnything()
    callback(False, None, False).WithSideEffects(  # pylint: disable=E1102
        self.CallbackCalled)
    self.mox.ReplayAll()
    updater.CheckForUpdateAsync(callback, 1)

    # See comments in _testUpdate for the explanation of event waiting.

    self.event.wait(1)
    self.mox.VerifyAll()


if __name__ == "__main__":
  unittest.main()
