#!/usr/bin/env python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import time
import xmlrpclib

import factory_common  # pylint: disable=W0611
from cros.factory.utils.process_utils import Spawn, TerminateOrKillProcess


class BoardNotSpecifiedError(Exception):
  pass


class BoardNotSupportedError(Exception):
  pass


class Servo(object):
  '''Object that wraps Servo board operations.

  This class wraps servod, which is the server process that controls Servo
  board.  It also acts as a client to servod and provides high-level APIs
  for use in factory testing.
  '''

  BOARD_CONFIG = {
    'link': {'vref': 'pp3300'},
    'daisy': {'vref': 'pp1800'},
    'daisy_spring': {'vref': 'pp1800'},
  }

  def __init__(self, servod_host='localhost', servod_port=9999,
               servo_serial='', board=''):
    self.servod_host = servod_host
    self.servod_port = servod_port
    self.servo_serial = servo_serial
    self.board = board
    self._servod = None
    self._server = None

  def StartServod(self, config=''):
    '''Starts servod.'''

    cmd = ['servod',
           '--host=%s' % self.servod_host,
           '--port=%d' % self.servod_port,
           ]
    if self.servo_serial:
      cmd.append('--serialname=%s' % self.servo_serial)
    if self.board:
      cmd.append('--board=%s' % self.board)
    if config:
      cmd.append('--config=%s' % config)
    self._servod = Spawn(cmd, log=True, sudo=True)
    return self._servod

  def StopServod(self):
    '''Stops servod.'''

    if self._servod:
      TerminateOrKillProcess(self._servod)
      self._servod = None

  def ConnectServod(self):
    '''Connects to servod.'''

    servod_address = 'http://%s:%d/' % (self.servod_host, self.servod_port)
    self._server = xmlrpclib.ServerProxy(servod_address)
    logging.info('Servod address: %s', servod_address)

  def HWInit(self):
    '''Resets Servo board settings.'''

    logging.debug('Servo hwinit')
    self._server.hwinit()

  def Get(self, name):
    '''Gets the value of a gpio from servod.'''

    value = self._server.get(name)
    logging.debug('Servo get %s return %s', name, value)
    return value

  def Set(self, name, value):
    '''Sets the value of a gpio using servod.'''

    logging.debug('Servo set %s:%s', name, value)
    self._server.set(name, value)

  def ColdReset(self, wait=1):
    '''Cold resets DUT.'''

    self.Set('cold_reset', 'on')
    time.sleep(wait)
    self.Set('cold_reset', 'off')

  def WarmReset(self, wait=1):
    '''Warm resets DUT.'''

    self.Set('warm_reset', 'on')
    time.sleep(wait)
    self.Set('warm_reset', 'off')

  def RecoveryBootDUT(self, wait=10):
    '''Boots DUT in recovery mode.'''

    self.Set('rec_mode', 'on')
    self.WarmReset()
    time.sleep(wait)
    self.Set('rec_mode', 'off')

  def SetupUSBForHost(self):
    '''Sets up USB on Servo board for host to use.'''

    self.Set('prtctl4_pwren', 'on')
    self.Set('dut_hub_pwren', 'on')
    self.Set('usb_mux_oe1', 'on')
    self.SwitchUSBToHost()
    self.Set('dut_hub_on', 'yes')

  def SwitchUSBToHost(self):
    '''Makes host see the USB key on Servo board.'''

    self.Set('usb_mux_sel1', 'servo_sees_usbkey')

  def SwitchUSBToDUT(self):
    '''Makes DUT see the USB key on Servo board.'''

    self.Set('usb_mux_sel1', 'dut_sees_usbkey')

  def FlashFirmware(self, firmware, verbose=False):
    '''Flashes DUT firmware via local attached Servo board.'''

    if not self.board:
      raise BoardNotSpecifiedError('Board not specified.')
    if not self.board in self.BOARD_CONFIG:
      raise BoardNotSupportedError(
          'Board %s not supported for flashing firmware' % self.board)
    self.Set('cold_reset', 'on')
    self.Set('spi2_vref', self.BOARD_CONFIG[self.board]['vref'])
    self.Set('spi2_buf_en', 'on')
    self.Set('spi2_buf_on_flex_en', 'on')
    self.Set('spi_hold', 'off')

    programmer = 'ft2232_spi:type=servo-v2'
    if self.servo_serial:
      programmer += ',serial=%s' % self.servo_serial
    cmd = ['flashrom', '--ignore-lock',
           '-w', firmware,
           '-p', programmer,
           ]
    if verbose:
      cmd.append('-V')
    Spawn(cmd, log=True, check_call=True, sudo=True)

    self.Set('spi2_vref', 'off')
    self.Set('spi2_buf_en', 'off')
    self.Set('spi2_buf_on_flex_en', 'off')

  def BootDUTFromImage(self, image_path, usb_dev,
                       usb_ready_wait=15, recovery_boot_wait=10,
                       dev_mode='on'):
    '''Copies image to USB key on local attached Servo board, and recovery boot
    DUT from the USB key.'''
    # TODO(chinyue): Auto-probe the USB key device on host.

    self.SetupUSBForHost()
    time.sleep(usb_ready_wait)
    cmd = ['pv', image_path, '|', 'sudo', 'dd', 'of=%s' % usb_dev,
           'iflag=fullblock', 'oflag=dsync', 'bs=8M']
    Spawn(' '.join(cmd), log=True, check_call=True, shell=True)
    self.SwitchUSBToDUT()
    self.Set('dev_mode', dev_mode)
    self.RecoveryBootDUT(wait=recovery_boot_wait)
