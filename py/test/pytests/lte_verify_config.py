# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Verifies the LTE module config.

Usage example::

  {
    "pytest_name": "lte_verify_config",
    "exclusive_resources": ["NETWORK"],
    "args": {
      "config_to_check": [
        ["AT_COMMAND_1", "RESPONSE_1"],
        [
          "AT_COMMAND_2",
          ["RESPONSE_2_LINE_1", "RESPONSE_2_LINE_2"]
        ]
      ],
      "modem_path": "ttyACM0",
      "attempts": 3
    }
  }
"""

import unittest

from cros.factory.test.rf import modem
from cros.factory.test import session
from cros.factory.utils.arg_utils import Arg

try:
  # TODO(littlecvr) Make dummy implementation.
  # pylint: disable=no-name-in-module
  from cros.factory.board import modem_utils
except ImportError:
  pass


class LTEVerifyConfig(unittest.TestCase):
  ARGS = [
      Arg('modem_path', str,
          'The path of the serial port. If not provided, will fall back to '
          'calling modem_utils.GetModem instead.', default=None),
      Arg('attempts', int,
          'Number of tries to enter factory mode, since the firmware AT+CFUN=4 '
          'is not stable enough.', default=2),
      Arg('config_to_check', list,
          'A list of tuples. For each tuple, the first element is the command '
          'and the second element is the expected response. Expected response '
          'can be a single string indicating only one line response or a list '
          'of strings indicating multiline response.')]

  def setUp(self):
    if self.args.modem_path:
      self.modem = modem.Modem(self.args.modem_path)
    else:
      self.modem = modem_utils.GetModem()

  def EnterFactoryMode(self):
    session.console.info('LTE: Entering factory test mode')
    self.modem = modem_utils.EnterFactoryMode(
        attempts=self.args.attempts)
    session.console.info('LTE: Entered factory test mode')

  def ExitFactoryMode(self):
    session.console.info('LTE: Exiting factory test mode')
    if self.modem:
      modem_utils.ExitFactoryMode(self.modem)
      session.console.info('LTE: Exited factory test mode')
    else:
      session.console.info('No modem object exists to exit')

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
