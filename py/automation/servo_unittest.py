#!/usr/bin/env python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mox
import servo
import unittest


class MockServerProxy(object):
  '''Mocks ServerProxy and the methods it wraps.'''

  def hwinit(self):
    pass

  def get(self, name):
    pass

  def set(self, name, value):
    pass


class ServoTest(unittest.TestCase):
  def setUp(self):
    '''Called before each test method, sets up mox for each test method.'''
    self.mox = mox.Mox()

  def tearDown(self):
    '''Called after each test method, unsets stubs and verifies mocks were
    used as expected.'''
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testStartServod(self):
    self.mox.StubOutWithMock(servo, 'Spawn')
    servo.Spawn(['servod', '--host=localhost', '--port=9999'],
                log=True, sudo=True)
    servo.Spawn(['servod', '--host=192.168.1.1', '--port=8888'],
                log=True, sudo=True)
    servo.Spawn(['servod', '--host=localhost', '--port=9999',
                 '--serialname=SERIAL'], log=True, sudo=True)
    servo.Spawn(['servod', '--host=localhost', '--port=9999',
                 '--board=BOARD', '--config=CONFIG'], log=True, sudo=True)
    self.mox.ReplayAll()

    servo.Servo().StartServod()
    servo.Servo(servod_host='192.168.1.1', servod_port=8888).StartServod()
    servo.Servo(servo_serial='SERIAL').StartServod()
    servo.Servo(board='BOARD').StartServod(config='CONFIG')

  def testConnectServod(self):
    self.mox.StubOutClassWithMocks(servo.xmlrpclib, 'ServerProxy')
    servo.xmlrpclib.ServerProxy('http://localhost:9999/')
    servo.xmlrpclib.ServerProxy('http://192.168.1.1:8888/')
    self.mox.ReplayAll()

    servo.Servo().ConnectServod()
    servo.Servo(servod_host='192.168.1.1', servod_port=8888).ConnectServod()

  def testServoCommands(self):
    # pylint: disable=W0212
    s = servo.Servo()
    s._server = self.mox.CreateMock(MockServerProxy)
    s._server.hwinit()
    s._server.get('name1').AndReturn('value1')
    s._server.set('name2', 'value2')
    s._server.set('usb_mux_sel1', 'servo_sees_usbkey')
    s._server.set('usb_mux_sel1', 'dut_sees_usbkey')
    # ColdReset set command sequence.
    s._server.set('cold_reset', 'on')
    s._server.set('cold_reset', 'off')
    # WarmReset set command sequence.
    s._server.set('warm_reset', 'on')
    s._server.set('warm_reset', 'off')
    # RecoveryBootDUT set command sequence.
    s._server.set('rec_mode', 'on')
    s._server.set('cold_reset', 'on')
    s._server.set('cold_reset', 'off')
    s._server.set('rec_mode', 'off')
    # SetupUSBForHost set command sequence.
    s._server.set('prtctl4_pwren', 'on')
    s._server.set('dut_hub_pwren', 'on')
    s._server.set('usb_mux_oe1', 'on')
    s._server.set('usb_mux_sel1', 'servo_sees_usbkey')
    s._server.set('dut_hub_on', 'yes')
    self.mox.ReplayAll()

    s.HWInit()
    s.Get('name1')
    s.Set('name2', 'value2')
    s.SwitchUSBToHost()
    s.SwitchUSBToDUT()
    s.ColdReset(wait=0)
    s.WarmReset(wait=0)
    s.RecoveryBootDUT(wait=0)
    s.SetupUSBForHost()

  def testFlashFirmwareBoardCheck(self):
    self.assertRaises(servo.BoardNotSpecifiedError,
                      servo.Servo().FlashFirmware,
                      '/path/to/firmware')
    self.assertRaises(servo.BoardNotSupportedError,
                      servo.Servo(board='someboard').FlashFirmware,
                      '/path/to/firmware')

  def _testFlashFirmware(self, servo_serial, programmer):
    # pylint: disable=W0212
    s = servo.Servo(board='link', servo_serial=servo_serial)
    s._server = self.mox.CreateMock(MockServerProxy)
    self.mox.StubOutWithMock(servo, 'Spawn')
    s._server.set('cold_reset', 'on')
    s._server.set('spi2_vref', 'pp3300')
    s._server.set('spi2_buf_en', 'on')
    s._server.set('spi2_buf_on_flex_en', 'on')
    s._server.set('spi_hold', 'off')
    servo.Spawn(['flashrom', '--ignore-lock', '-w', '/path/to/firmware',
                 '-p', programmer],
                log=True, check_call=True, sudo=True)
    s._server.set('spi2_vref', 'off')
    s._server.set('spi2_buf_en', 'off')
    s._server.set('spi2_buf_on_flex_en', 'off')
    self.mox.ReplayAll()

    s.FlashFirmware('/path/to/firmware')

  def testFlashFirmware(self):
    self._testFlashFirmware('', 'ft2232_spi:type=servo-v2')

  def testFlashFirmwareWithServoSerial(self):
    self._testFlashFirmware('SERIAL', 'ft2232_spi:type=servo-v2,serial=SERIAL')

  def testBootDUTFromImage(self):
    self.mox.StubOutWithMock(servo, 'Spawn')
    s = servo.Servo()
    self.mox.StubOutWithMock(s, 'SetupUSBForHost')
    self.mox.StubOutWithMock(s, 'SwitchUSBToDUT')
    self.mox.StubOutWithMock(s, 'Set')
    self.mox.StubOutWithMock(s, 'RecoveryBootDUT')
    s.SetupUSBForHost()
    servo.Spawn('pv /path/to/image | sudo dd of=/path/to/usb '
                'iflag=fullblock oflag=dsync bs=8M',
                log=True, check_call=True, shell=True)
    s.SwitchUSBToDUT()
    s.Set('dev_mode', 'on')
    s.RecoveryBootDUT(wait=0)
    self.mox.ReplayAll()

    s.BootDUTFromImage('/path/to/image', '/path/to/usb',
                       usb_ready_wait=0, recovery_boot_wait=0)


if __name__ == '__main__':
  unittest.main()
