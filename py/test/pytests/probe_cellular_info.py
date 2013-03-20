# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# DESCRIPTION :
# This factory test will probe the basic information of a cellular modem.
#
# For the iccid test, please note this test requires a SIM card,
# a test SIM is fine. The SIM does NOT need to have an account
# provisioned.

# Following parameters are provided via dargs:
# 'imei_re': The regular expression of expected IMEI, first group of the
#            regular expression will be extracted. None value to skip this
#            item.
# 'iccid_re': The regular expression of expected ICCID, first group of the
#             regular expression will be extracted. None value to skip this
#             item.
# 'modem_path': Path to the modem, for ex: /dev/ttyUSB0. Setting this implies
#               use AT command directly with the modem. Otherwise, flimflam
#               will handle the extraction.
#

import re
import serial as pyserial
import unittest

from cros.factory.event_log import Log
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test import utils
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager

_TEST_TITLE = test_ui.MakeLabel('SIM / IMEI / MEID Extraction',
                                u'数据机资讯提取')
DEVICE_NORMAL_RESPONSE = 'OK'


class Error(Exception):
  """Generic fatal error."""
  pass


class _Serial(object):
  '''Simple wrapper for pySerial.
  '''
  def __init__(self, dev_path):
    # Directly issue commands to the modem.
    self.serial = pyserial.Serial(dev_path, timeout=2)
    self.serial.read(self.serial.inWaiting())  # Empty the buffer.

  def read_response(self):
    '''Reads response from the modem until a timeout.'''
    line = self.serial.readline()
    factory.log('modem[ %r' % line)
    return line.rstrip('\r\n')

  def send_command(self, command):
    '''Sends a command to the modem and discards the echo.'''
    self.serial.write(command + '\r')
    factory.log('modem] %r' % command)
    self.read_response()

  def check_response(self, expected_re):
    '''Checks response with a regular expression returns a SRE_Match object.'''
    response = self.read_response()
    re_ret = re.search(expected_re, response)
    if not re_ret:
      raise Error('Expected %r but got %r' % (expected_re, response))
    return re_ret


class IMEITask(FactoryTask):
  def __init__(self, test): # pylint: disable=W0231
    self.test = test

  def Run(self):
    if not self.test.modem_path:
      modem_info = utils.CheckOutput(['modem', 'status'])
      imei = re.search(self.test.imei_re, modem_info).group(1)
    else:
      # Directly issue commands to the modem.
      modem = _Serial(self.test.modem_path)
      # Send an AT command and expect 'OK'
      modem.send_command('AT')
      modem.check_response(DEVICE_NORMAL_RESPONSE)
      modem.send_command('AT+CGSN')
      imei = modem.check_response(self.test.imei_re).group(1)
    Log('imei', imei=imei)
    factory.log('IMEI: %s' % imei)
    self.Stop()


class ICCIDTask(FactoryTask):
  def __init__(self, test): # pylint: disable=W0231
    self.test = test

  def Run(self):
    if not self.test.modem_path:
      modem_info = utils.CheckOutput(['modem', 'status'])
      iccid = re.search(self.test.iccid_re, modem_info).group(1)
    else:
      # Directly issue commands to the modem.
      modem = _Serial(self.test.modem_path)
      # Send an AT command and expect 'OK'
      modem.send_command('AT')
      modem.check_response(DEVICE_NORMAL_RESPONSE)
      modem.send_command('AT+ICCID?')
      iccid = modem.check_response(self.test.iccid_re).group(1)
    Log('iccid', iccid=iccid)
    factory.log('ICCID: %s' % iccid)
    self.Stop()


class StartTest(unittest.TestCase):
  def __init__(self, *args, **kwargs):
    super(StartTest, self).__init__(*args, **kwargs)
    self.task_list = []
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS('.start-font-size {font-size: 2em;}')
    self.template.SetTitle(_TEST_TITLE)

  def runTest(self):
    # Allow attributes to be defined outside __init__
    # pylint: disable=W0201
    args = self.test_info.args
    self.modem_path = args.get('modem_path', None)
    self.imei_re = args.get('imei_re', None)
    self.iccid_re = args.get('iccid_re', None)
    self.pin_command = args.get('pin_command', None)
    self.meid_re = args.get('meid_re', None)
    self.prompt = args.get('prompt', None)

    if self.prompt:
      # TODO(itspeter): add a prompt screen.
      raise NotImplementedError

    if self.imei_re:
      self.task_list.append(IMEITask(self))

    if self.iccid_re:
      self.task_list.append(ICCIDTask(self))

    if self.meid_re:
      # TODO(itspeter): Implment this extraction for CDMA.
      raise NotImplementedError

    FactoryTaskManager(self.ui, self.task_list).Run()
