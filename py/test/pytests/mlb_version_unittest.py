#!/usr/bin/python -Bu
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for mlb_version factory test."""

import mox
import unittest

import factory_common   # pylint: disable=W0611
from cros.factory import system
from cros.factory.test import phase
from cros.factory.test.dut.link import DUTLink
from cros.factory.test.pytests import mlb_version


class MockBoard(object):
  """A mock board class."""

  def __init__(self, version):
    self.version = version

  def GetBoardVersion(self):
    return self.version


class MLBVersionTestUnittest(unittest.TestCase):
  """Unit tests for mlb_version factory test."""

  def setUp(self):
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(system, 'GetBoard')
    self.mox.StubOutWithMock(phase, 'GetPhase')

    class FakeArgs(object):
      """A fake factory test args object."""
      expected_version = None

    self.test = mlb_version.MLBVersionTest()
    # TODO(hungte) The dut is now actually a link. Replace the GetBoard(dut) to
    # self.dut when we have finished to migration.
    self.test.dut = self.mox.CreateMock(DUTLink)
    self.test.args = FakeArgs()

  def tearDown(self):
    self.mox.UnsetStubs()

  def testNoArgs(self):
    proto2b_board = MockBoard('Proto2B')
    pvt3_board = MockBoard('PVT3')
    # Proto2b board in phase PROTO.
    system.GetBoard(self.test.dut).AndReturn(proto2b_board)
    phase.GetPhase().AndReturn(phase.PROTO)
    # Proto2b board in phase EVT.
    system.GetBoard(self.test.dut).AndReturn(proto2b_board)
    phase.GetPhase().AndReturn(phase.EVT)
    # Proto2b board in phase PVT_DOGFOOD
    system.GetBoard(self.test.dut).AndReturn(proto2b_board)
    phase.GetPhase().AndReturn(phase.PVT_DOGFOOD)
    # PVT3 board in phase PVT_DOGFOOD.
    system.GetBoard(self.test.dut).AndReturn(pvt3_board)
    phase.GetPhase().AndReturn(phase.PVT_DOGFOOD)
    # PVT3 board in phase PVT.
    system.GetBoard(self.test.dut).AndReturn(pvt3_board)
    phase.GetPhase().AndReturn(phase.PVT)

    self.mox.ReplayAll()

    # Proto2b board in phase PROTO. This should pass.
    self.test.runTest()
    # Proto2b board in phase EVT. This should fail due to mismatch version
    # prefix.
    self.assertRaisesRegexp(
        AssertionError,
        (r'In phase EVT, expect board version to start with EVT, but got board '
         r'version Proto2B'),
        self.test.runTest)
    # Proto2b board in phase PVT_DOGFOOD. This should fail due to mismatch
    # version prefix.
    self.assertRaisesRegexp(
        AssertionError,
        (r'In phase PVT_DOGFOOD, expect board version to start with '
         r'\(PVT\|MP\), but got board version Proto2B'),
        self.test.runTest)
    # PVT3 board in phase PVT_DOGFOOD. This should pass.
    self.test.runTest()
    # PVT3 board in phase PVT. This should pass.
    self.test.runTest()

    self.mox.VerifyAll()

  def testWithArgs(self):
    proto2b_board = MockBoard('Proto2B')
    pvt3_board = MockBoard('PVT3')
    # Expect to see board version 'Proto2B'.
    self.test.args.expected_version = 'Proto2B'
    # Test on Proto2b board.
    system.GetBoard(self.test.dut).AndReturn(proto2b_board)
    # Test on PVT3 board.
    system.GetBoard(self.test.dut).AndReturn(pvt3_board)

    self.mox.ReplayAll()

    # Test on Proto2b board. This should pass.
    self.test.runTest()
    # Test on PVT3 board. This should fail with mismatched board version.
    self.assertRaisesRegexp(
        AssertionError,
        (r'Board version mismatch\. Expect to see board version Proto2B, but '
         r'the actual board version is PVT3'),
        self.test.runTest)

    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()
