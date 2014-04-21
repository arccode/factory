#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""A command-line tool for reg code handling."""


import binascii
import logging
import random
import sys

import factory_common  # pylint: disable=W0611
from cros.factory.hacked_argparse import CmdArg, Command, ParseCmdline
from cros.factory.proto import reg_code_pb2
from cros.factory.system import vpd
from cros.factory.test import registration_codes
from cros.factory.test import utils
from cros.factory.test.registration_codes import RegistrationCode
from cros.factory.tools.build_board import BuildBoard


@Command('decode',
         CmdArg('regcode', metavar='REGCODE',
                help='Encoded registration code string'))
def Decode(options):
  reg_code = RegistrationCode(options.regcode)
  if reg_code.proto:
    print reg_code.proto
  else:
    print reg_code


@Command(
  'generate-dummy',
  CmdArg('--board', '-b', metavar='BOARD', required=True,
         help=('Board to generate codes for.  This must be exactly the '
               'same as the HWID board name, except lowercase.  For '
               'boards with variants (like "daisy_spring"), use only '
               'the variant name ("spring").')),
  CmdArg('--type', '-t', metavar='TYPE', required=True,
         choices=['unique', 'group'],
         help='The type of code to generate (choices: %(choices)s)'),
  CmdArg('--seed', '-s', metavar='INT', type=int, default=None,
         help='Seed to use for pseudo-random payload; defaults to clock'))
def GenerateDummy(options):
  print ('*** This may be used only to generate a code for testing, '
         'not for a real device.')
  yes_no = raw_input('*** Are you OK with that? (yes/no) ')
  if yes_no != 'yes':
    print 'Aborting.'
    sys.exit(1)

  random.seed(options.seed)
  proto = reg_code_pb2.RegCode()
  proto.content.code_type = (reg_code_pb2.UNIQUE_CODE
                             if options.type == 'unique'
                             else reg_code_pb2.GROUP_CODE)

  # Use this weird magic string for the first 16 characters to make it
  # obvious that this is a dummy code.  (Base64-encoding this string
  # results in a reg code that looks like
  # '=CiwKIP//////TESTING///////'...)
  proto.content.code = (
    '\xff\xff\xff\xff\xffLD\x93 \xd1\xbf\xff\xff\xff\xff\xff' + "".join(
    chr(random.getrandbits(8))
    for i in range(registration_codes.REGISTRATION_CODE_PAYLOAD_BYTES - 16)))
  proto.content.device = options.board.lower()
  proto.checksum = (
    binascii.crc32(proto.content.SerializeToString()) & 0xFFFFFFFF)

  encoded_string = '=' + binascii.b2a_base64(proto.SerializeToString()).strip()

  # Make sure the string can be parsed as a sanity check (this will catch,
  # e.g., invalid device names)
  reg_code = RegistrationCode(encoded_string)
  print
  print reg_code.proto
  print encoded_string


@Command(
  'check',
  CmdArg(
    '--unique-code', '-u', metavar='UNIQUE_CODE',
    help='Unique/user code to check (default: ubind_attribute RW VPD value)'),
  CmdArg(
    '--group-code', '-g', metavar='GROUP_CODE',
    help='Group code to check (default: gbind_attribute RW VPD value)'),
  CmdArg(
    '--board', '-b', metavar='BOARD',
    help='Board to check (default: from .default_board or lsb-release)'))
def Check(options):
  if not options.board:
    options.board = BuildBoard().short_name
  logging.info('Device name: %s', options.board)

  rw_vpd = None
  success = True

  for code_type, vpd_attribute, code in (
      (RegistrationCode.Type.UNIQUE_CODE,
       'ubind_attribute', options.unique_code),
      (RegistrationCode.Type.GROUP_CODE,
       'gbind_attribute', options.group_code)):

    if not code:
      if rw_vpd is None:
        if utils.in_chroot():
          sys.stderr.write('error: cannot read VPD from chroot; use -u/-g\n')
          sys.exit(1)

        rw_vpd = vpd.rw.GetAll()
        code = rw_vpd.get(vpd_attribute)
      if not code:
        sys.stderr.write('error: %s is not present in RW VPD\n' %
                         vpd_attribute)
        sys.exit(1)

    try:
      registration_codes.CheckRegistrationCode(code, code_type, options.board)
      logging.info('%s: success', code_type)
    except registration_codes.RegistrationCodeException as e:
      success = False
      logging.error('%s: failed: %s', code_type, str(e))

  sys.exit(0 if success else 1)


def main():
  logging.basicConfig(level=logging.INFO)
  options = ParseCmdline('Registration code tool.')
  options.command(options)


if __name__ == '__main__':
  main()
