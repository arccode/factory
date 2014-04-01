#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""A command-line tool for reg code handling."""


import factory_common  # pylint: disable=W0611
from cros.factory.hacked_argparse import CmdArg, Command, ParseCmdline
from cros.factory.test.registration_codes import RegistrationCode


@Command('decode',
         CmdArg('regcode', metavar='REGCODE',
                help='Encoded registration code string'))
def Decode(options):
  reg_code = RegistrationCode(options.regcode)
  if reg_code.proto:
    print reg_code.proto
  else:
    print reg_code


def main():
  options = ParseCmdline('Registration code tool.')
  options.command(options)


if __name__ == '__main__':
  main()
