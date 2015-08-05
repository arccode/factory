#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest
import sys

import factory_common

from cros.factory.hacked_argparse import Command, ParseCmdline, CmdArg

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
  sys.argv=['cmd'] + argv.split()
  result = vars(ParseCmdline('', *args))
  del result['command']
  return result

class HackedArgparseTest(unittest.TestCase):

  def testSubcommand(self):
    with self.assertRaises(SystemExit):
      Parse('')
    self.assertEquals({'command_name': 'do_this',
                       'defarg': '42',
                       'arg': None,
                       'foo': None},
                      Parse('do_this'))
    self.assertEquals({'command_name': 'do_that',
                       'defarg': '42',
                       'arg': None,
                       'bar': None},
                      Parse('do_that'))
    self.assertEquals({'command_name': 'do_this',
                       'defarg': '123',
                       'arg': 'abc',
                       'foo': None},
                      Parse('--defarg=123 --arg=abc do_this'))
    self.assertEquals({'command_name': 'do_this',
                       'defarg': '234',
                       'arg': 'xyz',
                       'foo': None},
                      Parse('--defarg=123 --arg=abc do_this --defarg=234 --arg=xyz'))
    self.assertEquals({'command_name': 'do_this',
                       'defarg': '234',
                       'arg': 'xyz',
                       'foo': None},
                      Parse('do_this --defarg=234 --arg=xyz'))


if __name__ == '__main__':
  unittest.main()
