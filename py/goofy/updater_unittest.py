#!/usr/bin/env python
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import threading
import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy import updater
from cros.factory.test import factory
from cros.factory.test import shopfloor


class CheckForUpdateTest(unittest.TestCase):

  def setUp(self):
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.UnsetStubs()

  def _testUpdate(self, local_version):
    self.mox.StubOutWithMock(factory, 'get_toolkit_version')
    factory.get_toolkit_version().AndReturn(local_version)

    self.mox.StubOutWithMock(shopfloor, 'get_instance')
    fake_shopfloor = self.mox.CreateMockAnything()
    shopfloor.get_instance(
        detect=True, timeout=3, quiet=False).AndReturn(fake_shopfloor)

    self.mox.StubOutWithMock(shopfloor, 'GetUpdateFromCROSPayload')
    shopfloor.GetUpdateFromCROSPayload(
        'toolkit', proxy=fake_shopfloor).AndReturn(
            ({'version': '11111'}, {}, NotImplemented))

    self.mox.ReplayAll()
    self.assertEquals(updater.CheckForUpdate(3),
                      ('11111', '11111' != local_version))
    self.mox.VerifyAll()

  def testMustUpdate(self):
    self._testUpdate('00000')

  def testNotUpdate(self):
    self._testUpdate('11111')


class CheckForUpdateAsyncTest(unittest.TestCase):
  """Test CheckForUpdateAsync with mocked CheckForUpdate and other functions."""

  def CallbackCalled(self, *unused_args, **unused_kwargs):
    """Arguments of this function are dummy."""
    self.event.set()

  def setUp(self):
    self.mox = mox.Mox()
    self.event = threading.Event()
    self.event.clear()

  def tearDown(self):
    self.mox.UnsetStubs()

  def _testUpdate(self, available):
    """Provides basic testing flow for testMustUpdate and testNotUpdate."""
    self.mox.StubOutWithMock(updater, 'CheckForUpdate')
    updater.CheckForUpdate(1).AndReturn(('11111', available))
    callback = self.mox.CreateMockAnything()
    # pylint: disable=not-callable
    callback(True, '11111', available).WithSideEffects(self.CallbackCalled)
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
    # pylint: disable=not-callable
    callback(False, None, False).WithSideEffects(self.CallbackCalled)
    self.mox.ReplayAll()
    updater.CheckForUpdateAsync(callback, 1)

    # See comments in _testUpdate for the explanation of event waiting.

    self.event.wait(1)
    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()
