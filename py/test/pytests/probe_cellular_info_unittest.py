#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Probes information from 'modem status'.

Requested data are probed, written to the event log, and saved to device data.
"""

import mox
import unittest2

import factory_common  # pylint: disable=W0611
from cros.factory.test.pytests import probe_cellular_info
from cros.factory.test.args import Args


class ProbeCellularInfoTestTest(unittest2.TestCase):
  def setUp(self):
    self.test = probe_cellular_info.ProbeCellularInfoTest()
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(probe_cellular_info, 'CheckOutput')
    self.mox.StubOutWithMock(probe_cellular_info, 'Log')
    self.mox.StubOutWithMock(probe_cellular_info, 'UpdateDeviceData')

  def tearDown(self):
    try:
      self.mox.VerifyAll()
    finally:
      self.mox.UnsetStubs()

  def testValid(self):
    stdout = """
Modem /org/chromium/ModemManager/Gobi/1:
  GetStatus:
    imei: 838293836198373
    meid: Q9298301CDF827
"""

    probe_cellular_info.CheckOutput(['modem', 'status'], log=True).AndReturn(
        stdout)
    probe_cellular_info.Log(
        'cellular_info', modem_status_stdout=stdout,
        imei='838293836198373', meid='Q9298301CDF827')
    probe_cellular_info.UpdateDeviceData({'imei': '838293836198373',
                                          'meid': 'Q9298301CDF827'})
    self.mox.ReplayAll()

    self.test.args = Args(*self.test.ARGS).Parse({})
    self.test.runTest()

  def testMissingIMEI(self):
    stdout = """
Modem /org/chromium/ModemManager/Gobi/1:
  GetStatus:
    meid: Q9298301CDF827
"""

    probe_cellular_info.CheckOutput(['modem', 'status'], log=True).AndReturn(
        stdout)
    probe_cellular_info.Log(
        'cellular_info', modem_status_stdout=stdout,
        imei=None, meid='Q9298301CDF827')
    self.mox.ReplayAll()

    self.test.args = Args(*self.test.ARGS).Parse({})
    self.assertRaisesRegexp(AssertionError, r"Missing elements.+: \['imei'\]",
                            self.test.runTest)

  def testBlankIMEI(self):
    stdout = """
Modem /org/chromium/ModemManager/Gobi/1:
  GetStatus:
    imei: #
    meid: Q9298301CDF827
""".replace("#", "")
    # Remove hash mark; necessary to make white-space check pass

    probe_cellular_info.CheckOutput(['modem', 'status'], log=True).AndReturn(
        stdout)
    probe_cellular_info.Log(
        'cellular_info', modem_status_stdout=stdout,
        imei=None, meid='Q9298301CDF827')
    self.mox.ReplayAll()

    self.test.args = Args(*self.test.ARGS).Parse({})
    self.assertRaisesRegexp(AssertionError, r"Missing elements.+: \['imei'\]",
                            self.test.runTest)


if __name__ == '__main__':
  unittest2.main()
