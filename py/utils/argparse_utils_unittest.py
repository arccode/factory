#!/usr/bin/env python3
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import sys
import unittest
from unittest import mock

from cros.factory.utils.argparse_utils import CmdArg
from cros.factory.utils.argparse_utils import Command
from cros.factory.utils.argparse_utils import ParseCmdline


@Command('do_this',
         CmdArg('--foo'))
def DoThis():
  pass

@Command('do_that',
         CmdArg('--bar'))
def DoThat():
  pass

args = [CmdArg('--defarg', default='42'),
        CmdArg('--arg')]

def Parse(argv):
  sys.argv = ['cmd'] + argv.split()
  result = vars(ParseCmdline('', *args))
  if 'command' in result:
    del result['command']
  return result

class HackedArgparseTest(unittest.TestCase):

  @mock.patch('cros.factory.utils.argparse_utils.HackedArgParser.error')
  def testSubcommand(self, error_mock):
    error_mock.side_effect = Exception

    with self.assertRaises(Exception):
      Parse('')
    self.assertEqual(
        {
            'command_name': 'do_this',
            'defarg': '42',
            'arg': None,
            'foo': None
        }, Parse('do_this'))
    self.assertEqual(
        {
            'command_name': 'do_that',
            'defarg': '42',
            'arg': None,
            'bar': None
        }, Parse('do_that'))
    self.assertEqual(
        {
            'command_name': 'do_this',
            'defarg': '123',
            'arg': 'abc',
            'foo': None
        }, Parse('--defarg=123 --arg=abc do_this'))
    self.assertEqual(
        {
            'command_name': 'do_this',
            'defarg': '234',
            'arg': 'xyz',
            'foo': None
        }, Parse('--defarg=123 --arg=abc do_this --defarg=234 --arg=xyz'))
    self.assertEqual(
        {
            'command_name': 'do_this',
            'defarg': '234',
            'arg': 'xyz',
            'foo': None
        }, Parse('do_this --defarg=234 --arg=xyz'))


if __name__ == '__main__':
  unittest.main()
