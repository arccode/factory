#!/usr/bin/env python2
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Probes information from 'modem status'.

Requested data are probed, written to the event log, and saved to device data.
"""

import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.test import device_data
from cros.factory.test import event_log
from cros.factory.test.pytests import probe_cellular_info
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Args
from cros.factory.utils import process_utils


class ProbeCellularInfoTestTest(unittest.TestCase):

  def setUp(self):
    self.test = probe_cellular_info.ProbeCellularInfoTest()
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(process_utils, 'CheckOutput')
    self.mox.StubOutWithMock(event_log, 'Log')
    self.mox.StubOutWithMock(testlog, 'LogParam')
    self.mox.StubOutWithMock(device_data, 'UpdateDeviceData')

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

    process_utils.CheckOutput(['modem', 'status'], log=True).AndReturn(stdout)
    event_log.Log(
        'cellular_info', modem_status_stdout=stdout,
        imei='838293836198373', meid='Q9298301CDF827')
    testlog.LogParam('modem_status_stdout', stdout)
    testlog.LogParam('imei', '838293836198373')
    testlog.LogParam('meid', 'Q9298301CDF827')
    device_data.UpdateDeviceData({'component.cellular.imei': '838293836198373',
                                  'component.cellular.meid': 'Q9298301CDF827'})
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

    process_utils.CheckOutput(['modem', 'status'], log=True).AndReturn(stdout)
    event_log.Log(
        'cellular_info', modem_status_stdout=stdout,
        lte_imei='359636040066332', lte_iccid='89148000000328035895')
    testlog.LogParam('modem_status_stdout', stdout)
    testlog.LogParam('lte_imei', '359636040066332')
    testlog.LogParam('lte_iccid', '89148000000328035895')
    device_data.UpdateDeviceData({
        'component.cellular.lte_imei': '359636040066332',
        'component.cellular.lte_iccid': '89148000000328035895'})
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

    process_utils.CheckOutput(['modem', 'status'], log=True).AndReturn(stdout)
    event_log.Log(
        'cellular_info', modem_status_stdout=stdout,
        imei=None, meid='Q9298301CDF827')
    testlog.LogParam('modem_status_stdout', stdout)
    testlog.LogParam('imei', None)
    testlog.LogParam('meid', 'Q9298301CDF827')
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
""".replace('#', '')
    # Remove hash mark; necessary to make white-space check pass

    process_utils.CheckOutput(['modem', 'status'], log=True).AndReturn(stdout)
    event_log.Log(
        'cellular_info', modem_status_stdout=stdout,
        imei=None, meid='Q9298301CDF827')
    testlog.LogParam('modem_status_stdout', stdout)
    testlog.LogParam('imei', None)
    testlog.LogParam('meid', 'Q9298301CDF827')
    self.mox.ReplayAll()

    self.test.args = Args(*self.test.ARGS).Parse({})
    self.assertRaisesRegexp(AssertionError, r"Missing elements.+: \['imei'\]",
                            self.test.runTest)


if __name__ == '__main__':
  unittest.main()
