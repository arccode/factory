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
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.pytests import probe_cellular_info
from cros.factory.test.args import Args


class ProbeCellularInfoTestTest(unittest.TestCase):
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

  def testValidLTE(self):
    stdout = """
Modem /org/freedesktop/ModemManager1/Modem/0:
  GetStatus:
    state: 7
  Properties:
    Sim: /org/freedesktop/ModemManager1/SIM/0
    SupportedCapabilities: 8
    CurrentCapabilities: 8
    MaxBearers: 1
    MaxActiveBearers: 1
    Manufacturer: ALTAIR-SEMICONDUCTOR
    Model: ALT3100
    Revision: ALT3100_04_05_06_00_58_TF
    DeviceIdentifier: 14336085e42e1bc2ea8da6e1f52a86f55f2a54b1
    Device: /sys/devices/s5p-ehci/usb1/1-2/1-2.2
    Drivers: cdc_ether, cdc_acm
    Plugin: Altair LTE
    PrimaryPort: ttyACM0
    EquipmentIdentifier: 359636040066332
    UnlockRequired: 1
    UnlockRetries: 3, 3, 10, 10
    State: 7
    StateFailedReason: 0
    AccessTechnologies: 0
    SignalQuality: 0, false
    OwnNumbers: +16503189999
    PowerState: 3
    SupportedModes: 8, 0
    CurrentModes: 8, 0
    SupportedBands: 43
    CurrentBands: 43
    SupportedIpFamilies: 1
  3GPP:
    Imei: 359636040066332
    RegistrationState: 4
    OperatorCode:
    OperatorName:
    EnabledFacilityLocks: 0
  CDMA:
  SIM /org/freedesktop/ModemManager1/SIM/0:
    SimIdentifier: 89148000000328035895
    Imsi: 204043996791870
    OperatorIdentifier: 20404
    OperatorName:
"""

    probe_cellular_info.CheckOutput(['modem', 'status'], log=True).AndReturn(
        stdout)
    probe_cellular_info.Log(
        'cellular_info', modem_status_stdout=stdout,
        lte_imei='359636040066332', lte_iccid='89148000000328035895')
    probe_cellular_info.UpdateDeviceData({'lte_imei': '359636040066332',
                                          'lte_iccid': '89148000000328035895'})
    self.mox.ReplayAll()

    self.test.args = Args(*self.test.ARGS).Parse(
        {'probe_imei': False,
         'probe_meid': False,
         'probe_lte_imei': True,
         'probe_lte_iccid': True})
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
  unittest.main()
