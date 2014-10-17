# -*- coding: utf-8 -*-
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Verifies the LTE module config.

Usage example::

  FactoryTest(
      exclusive=['NETWORKING'],
      id='LTEVerifyConfig',
      label_zh=u'确认 LTE 参数',
      pytest_name='lte_verify_config',
      dargs={
          'modem_path': 'ttyACM0',
          'attempts': 3,
          'config_to_check': [
              # Single line response example.
              ('AT_COMMAND_1', 'RESPONSE_1'),
              # Multi-line response example.
              ('AT_COMMAND_2', ['RESPONSE_2_LINE_1', RESPONSE_2_LINE_2]),
"""

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test.args import Arg
from cros.factory.rf import modem

try:
  # TODO(littlecvr) Make dummy implementation.
  from cros.factory.board import modem_utils  # pylint: disable=E0611
except ImportError:
  pass


class LTEVerifyConfig(unittest.TestCase):
  ARGS = [
    Arg('modem_path', str, 'The path of the serial port.'),
    Arg('attempts', int,
        'Number of tries to enter factory mode, since the firmware AT+CFUN=4 '
        'is not stable enough.', default=2),
    Arg('config_to_check', list, 'A list of tuples. For each tuple, the first '
        'element is the command and the second element is the expected '
        'response. Expected response can be a single string indicating only '
        'one line response or a list of strings indicating multiline response.')
  ]

  def setUp(self):
    self.modem = modem.Modem(self.args.modem_path)

  def EnterFactoryMode(self):
    factory.console.info('LTE: Entering factory test mode')
    self.modem = modem_utils.EnterFactoryMode(
        attempts=self.args.attempts)
    factory.console.info('LTE: Entered factory test mode')

  def ExitFactoryMode(self):
    factory.console.info('LTE: Exiting factory test mode')
    if self.modem:
      modem_utils.ExitFactoryMode(self.modem)
      factory.console.info('LTE: Exited factory test mode')
    else:
      factory.console.info('No modem object exists to exit')

  def runTest(self):
    try:
      self.EnterFactoryMode()
      for cmd, expected_response in self.args.config_to_check:
        if isinstance(expected_response, str):
          expected_response = [expected_response, 'OK']
        else:
          expected_response += ['OK']
        response = self.modem.SendCommandWithCheck(cmd)
        if response != expected_response:
          raise ValueError(
              'Should get %s but got %s' % (expected_response, response))
    finally:
      self.ExitFactoryMode()
