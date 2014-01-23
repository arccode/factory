#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for ChromeosBoard."""


import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.board.chromeos_board import ChromeOSBoard
from cros.factory.system.board import Board, BoardException


# pylint: disable=W0212

class ChromeOSBoardTest(unittest.TestCase):
  """Unittest for ChromeOSBoard."""
  def setUp(self):
    self.mox = mox.Mox()
    self.board = ChromeOSBoard()
    self.mox.StubOutWithMock(self.board, '_CallECTool')
    self.mox.StubOutWithMock(self.board, '_Spawn')

  def tearDown(self):
    self.mox.UnsetStubs()

  def testGetTemperatures(self):
    _MOCK_TEMPS = '\n'.join([
        '0: 273',
        '1: 283',
        '2: 293',
        '3: 303',
        '4: 313',
        '5: 323'])
    self.board._CallECTool(['temps', 'all'], check=False).AndReturn(_MOCK_TEMPS)
    self.mox.ReplayAll()
    self.assertEquals(self.board.GetTemperatures(), [0, 10, 20, 30, 40, 50])
    self.mox.VerifyAll()

  def testGetTemperaturesNotCalibrated(self):
    _MOCK_TEMPS = '\n'.join([
        '0: 273',
        '1: 283',
        'Sensor 2 not calibrated',
        '3: 303',
        '4: 313',
        '5: 323'])
    self.board._CallECTool(['temps', 'all'], check=False).AndReturn(_MOCK_TEMPS)
    self.mox.ReplayAll()
    self.assertEquals(self.board.GetTemperatures(), [0, 10, None, 30, 40, 50])
    self.mox.VerifyAll()

  def testGetTemperatureMainIndex(self):
    _MOCK_TEMPS_INFO = '\n'.join([
        '0: 0 I2C_CPU-Die',
        '1: 255 I2C_CPU-Object',
        '2: 1 I2C_PCH-Die',
        '3: 2 I2C_PCH-Object',
        '4: 1 I2C_DDR-Die',
        '5: 2 I2C_DDR-Object',
        '6: 1 I2C_Charger-Die',
        '7: 2 I2C_Charger-Object',
        '8: 1 ECInternal',
        '9: 0 PECI'
    ])
    self.board._CallECTool(['tempsinfo', 'all'],
                           check=False).AndReturn(_MOCK_TEMPS_INFO)
    self.mox.ReplayAll()
    self.assertEquals(self.board.GetMainTemperatureIndex(), 9)
    self.mox.VerifyAll()

  def testGetFanRPM(self):
    _MOCK_FAN_RPM = 'Current fan RPM: 2974\n'
    self.board._CallECTool(['pwmgetfanrpm'],
                           check=False).AndReturn(_MOCK_FAN_RPM)
    self.mox.ReplayAll()
    self.assertEquals(self.board.GetFanRPM(), 2974)
    self.mox.VerifyAll()

  def testSetFanRPM(self):
    self.board._Spawn(['ectool', 'pwmsetfanrpm', '12345'],
                      check_call=True, ignore_stdout=True,
                      log_stderr_on_error=True)
    self.mox.ReplayAll()
    self.board.SetFanRPM(12345)
    self.mox.VerifyAll()

  def testSetFanRPMAuto(self):
    self.board._Spawn(['ectool', 'autofanctrl', 'on'],
                      check_call=True, ignore_stdout=True,
                      log_stderr_on_error=True)
    self.mox.ReplayAll()
    self.board.SetFanRPM(self.board.AUTO)
    self.mox.VerifyAll()

  def testI2CRead(self):
    _MOCK_I2C_READ = 'Read from I2C port 0 at 0x12 offset 0x12 = 0xf912'
    self.board._CallECTool(['i2cread', '16', '0', '18',
                           '18']).AndReturn(_MOCK_I2C_READ)
    self.mox.ReplayAll()
    self.assertEquals(self.board.I2CRead(0, 0x12, 0x12), 0xf912)
    self.mox.VerifyAll()

  def testI2CWrite(self):
    self.board._CallECTool(['i2cwrite', '16', '0', '18', '18', '0'])
    self.mox.ReplayAll()
    self.board.I2CWrite(0, 0x12, 0x12, 0)
    self.mox.VerifyAll()

  def testGetChargerCurrent(self):
    _MOCK_I2C_READ = 'Read from I2C port 0 at 0x12 offset 0x14 = 0x1000'
    self.board._CallECTool(['i2cread', '16', '0', '18',
                            '20']).AndReturn(_MOCK_I2C_READ)
    self.mox.ReplayAll()
    self.assertEquals(self.board.GetChargerCurrent(), 0x1000)
    self.mox.VerifyAll()

  def testGetBatteryCurrent(self):
    _MOCK_I2C_READ = 'Read from I2C port 0 at 0x16 offset 0xa = 0x1000'
    self.board._CallECTool(['i2cread', '16', '0', '22',
                            '10']).AndReturn(_MOCK_I2C_READ)
    self.mox.ReplayAll()
    self.assertEquals(self.board.GetBatteryCurrent(), 0x1000)
    self.mox.VerifyAll()

  def testGetECVersion(self):
    _MOCK_VERSION = '\n'.join([
        'vendor               | ti',
        'name                 | lm4fs1gh5bb',
        'fw_version           | link_v1.1.227-3b0e131'])

    class Dummy(object):
      """A dummy class to mock Spawn output."""
      def __init__(self):
        self.stdout_data = None
    dummy = Dummy()
    dummy.stdout_data = _MOCK_VERSION

    self.board._Spawn(['mosys', 'ec', 'info', '-l'], ignore_stderr=True,
                      read_stdout=True).AndReturn(dummy)
    self.mox.ReplayAll()
    self.assertEquals(self.board.GetECVersion(), 'link_v1.1.227-3b0e131')
    self.mox.VerifyAll()

  def testGetECConsoleLog(self):
    _MOCK_LOG = '\n'.join([
        '[hostcmd 0x20]',
        '[hostcmd 0x60]',
        '[charge state idle -> charge]'])

    self.board._CallECTool(['console'], check=False).AndReturn(_MOCK_LOG)
    self.mox.ReplayAll()
    self.assertEquals(self.board.GetECConsoleLog(), _MOCK_LOG)
    self.mox.VerifyAll()

  def testGetECPanicInfo(self):
    _MOCK_PANIC = '\n'.join([
        'Saved panic data: (NEW)',
        '=== PROCESS EXCEPTION: 06 === xPSR: 21000000 ======',
        'r0 :00000000 r1 :0800a394 r2 :40013800 r3 :0000cdef',
        'r4 :00000000 r5 :00000011 r6 :20001aa0 r7 :00000000',
        'r8 :00000000 r9 :20001ab0 r10:00000000 r11:00000000',
        'r12:00000000 sp :20000fe0 lr :0800023d pc :08000242'])

    self.board._CallECTool(['panicinfo'], check=False).AndReturn(_MOCK_PANIC)
    self.mox.ReplayAll()
    self.assertEquals(self.board.GetECPanicInfo(), _MOCK_PANIC)
    self.mox.VerifyAll()

  def testCharge(self):
    self.board._CallECTool(['chargecontrol', 'normal'])
    self.mox.ReplayAll()
    self.board.SetChargeState(Board.ChargeState.CHARGE)
    self.mox.VerifyAll()

  def testDischarge(self):
    self.board._CallECTool(['chargecontrol', 'discharge'])
    self.mox.ReplayAll()
    self.board.SetChargeState(Board.ChargeState.DISCHARGE)
    self.mox.VerifyAll()

  def testStopCharge(self):
    self.board._CallECTool(['chargecontrol', 'idle'])
    self.mox.ReplayAll()
    self.board.SetChargeState(Board.ChargeState.IDLE)
    self.mox.VerifyAll()

  def testProbeEC(self):
    self.board._CallECTool(['hello']).AndReturn('EC says hello')
    self.mox.ReplayAll()
    self.board.ProbeEC()
    self.mox.VerifyAll()

  def testProbeECFail(self):
    self.board._CallECTool(['hello']).AndReturn('EC dooes not say hello')
    self.mox.ReplayAll()
    self.assertRaises(BoardException, self.board.ProbeEC)
    self.mox.VerifyAll()

  def testProbeBattery(self):
    _BATTERY_INFO = """Battery info:
  OEM name:          FOO
  Design capacity:   8000 mAh
"""
    self.board._CallECTool(['battery']).AndReturn(_BATTERY_INFO)
    self.mox.ReplayAll()
    self.assertEqual(8000, self.board.GetBatteryDesignCapacity())
    self.mox.VerifyAll()

  def testProbeBatteryFail(self):
    _BATTERY_INFO = """Battery info:
  OEM name:          FOO
"""
    self.board._CallECTool(['battery']).AndReturn(_BATTERY_INFO)
    self.mox.ReplayAll()
    self.assertRaises(BoardException, self.board.GetBatteryDesignCapacity)
    self.mox.VerifyAll()

  def testProbeBatteryFailZeroBatteryCapacity(self):
    _BATTERY_INFO = """Battery info:
  OEM name:          FOO
  Design capacity:   0 mAh
"""
    self.board._CallECTool(['battery']).AndReturn(_BATTERY_INFO)
    self.mox.ReplayAll()
    self.assertRaises(BoardException, self.board.GetBatteryDesignCapacity)
    self.mox.VerifyAll()

  def testSetLEDColor(self):
    self.board._CallECTool(['led', 'battery', 'red'])
    self.board._CallECTool(['led', 'battery', 'yellow'])
    self.board._CallECTool(['led', 'battery', 'green'])

    self.board._CallECTool(['led', 'battery', 'green=255'])
    self.board._CallECTool(['led', 'battery', 'green=128'])
    self.board._CallECTool(['led', 'battery', 'green=0'])

    self.board._CallECTool(['led', 'power', 'green'])

    self.board._CallECTool(['led', 'battery', 'auto'])
    # brightness does not take effect.
    self.board._CallECTool(['led', 'battery', 'auto'])

    # Turn off battery LED.
    self.board._CallECTool(['led', 'battery', 'off'])
    self.board._CallECTool(['led', 'battery', 'off'])

    self.mox.ReplayAll()
    self.board.SetLEDColor(Board.LEDColor.RED)
    self.board.SetLEDColor(Board.LEDColor.YELLOW)
    self.board.SetLEDColor(Board.LEDColor.GREEN)

    self.board.SetLEDColor(Board.LEDColor.GREEN, brightness=100)
    self.board.SetLEDColor(Board.LEDColor.GREEN, brightness=50)
    self.board.SetLEDColor(Board.LEDColor.GREEN, brightness=0)

    self.board.SetLEDColor(Board.LEDColor.GREEN, led_name='power')

    self.board.SetLEDColor(Board.LEDColor.AUTO)
    self.board.SetLEDColor(Board.LEDColor.AUTO, brightness=0)

    self.board.SetLEDColor(Board.LEDColor.OFF)
    self.board.SetLEDColor(Board.LEDColor.OFF, brightness=100)
    self.mox.VerifyAll()

  def testSetLEDColorInvalidInput(self):
    with self.assertRaisesRegexp(ValueError, 'Invalid color'):
      self.board.SetLEDColor('invalid color')
    with self.assertRaisesRegexp(TypeError, 'Invalid brightness'):
      self.board.SetLEDColor(Board.LEDColor.RED, brightness='1')
    with self.assertRaisesRegexp(ValueError, 'brightness out-of-range'):
      self.board.SetLEDColor(Board.LEDColor.RED, brightness=255)

  def testSetLEDColorUnsupportedBoard(self):
    self.board._CallECTool(['led', 'battery', 'red']).AndRaise(
        BoardException('EC returned error 99'))
    self.mox.ReplayAll()
    self.board.SetLEDColor(Board.LEDColor.RED)
    self.mox.VerifyAll()

  def testGetPartition(self):
    class Dummy(object):
      """A dummy class to mock Spawn output."""
      def __init__(self):
        self.stdout_data = None

    dummy_mmcblk0 = Dummy()
    dummy_mmcblk0.stdout_data = '/dev/mmcblk0'
    for _ in xrange(5):
      self.board._Spawn(
          ['rootdev', '-d'], check_output=True).AndReturn(dummy_mmcblk0)

    dummy_sda = Dummy()
    dummy_sda.stdout_data = '/dev/sda'
    for _ in xrange(5):
      self.board._Spawn(
          ['rootdev', '-d'], check_output=True).AndReturn(dummy_sda)

    self.mox.ReplayAll()

    self.assertEquals(self.board.GetPartition(Board.Partition.STATEFUL),
                      '/dev/mmcblk0p1')
    self.assertEquals(self.board.GetPartition(Board.Partition.FACTORY_KERNEL),
                      '/dev/mmcblk0p2')
    self.assertEquals(self.board.GetPartition(Board.Partition.FACTORY_ROOTFS),
                      '/dev/mmcblk0p3')
    self.assertEquals(self.board.GetPartition(Board.Partition.RELEASE_KERNEL),
                      '/dev/mmcblk0p4')
    self.assertEquals(self.board.GetPartition(Board.Partition.RELEASE_ROOTFS),
                      '/dev/mmcblk0p5')

    self.assertEquals(self.board.GetPartition(Board.Partition.STATEFUL),
                      '/dev/sda1')
    self.assertEquals(self.board.GetPartition(Board.Partition.FACTORY_KERNEL),
                      '/dev/sda2')
    self.assertEquals(self.board.GetPartition(Board.Partition.FACTORY_ROOTFS),
                      '/dev/sda3')
    self.assertEquals(self.board.GetPartition(Board.Partition.RELEASE_KERNEL),
                      '/dev/sda4')
    self.assertEquals(self.board.GetPartition(Board.Partition.RELEASE_ROOTFS),
                      '/dev/sda5')

    self.mox.VerifyAll()

if __name__ == '__main__':
  unittest.main()
