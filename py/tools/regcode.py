#!/usr/bin/env python3
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""A command-line tool for reg code handling."""

from __future__ import print_function

import base64
import binascii
import logging
import random
import sys

from six.moves import input

from cros.factory.device import device_utils
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.proto import reg_code_pb2
from cros.factory.test.rules import registration_codes
from cros.factory.test.rules.registration_codes import RegistrationCode
from cros.factory.utils.argparse_utils import CmdArg
from cros.factory.utils.argparse_utils import Command
from cros.factory.utils.argparse_utils import ParseCmdline
from cros.factory.utils.cros_board_utils import BuildBoard
from cros.factory.utils import sys_utils


@Command('decode',
         CmdArg('regcode', metavar='REGCODE',
                help='Encoded registration code string'))
def Decode(options):
  reg_code = RegistrationCode(options.regcode)
  if reg_code.proto:
    print(reg_code.proto)
  else:
    print(reg_code)


@Command(
    'generate-dummy',
    CmdArg('--project', '-p', metavar='PROJECT', required=True,
           help=('Project to generate codes for.  This must be exactly the '
                 'same as the HWID project name, except lowercase.')),
    CmdArg('--type', '-t', metavar='TYPE', required=True,
           choices=['unique', 'group'],
           help='The type of code to generate (choices: %(choices)s)'),
    CmdArg('--seed', '-s', metavar='INT', type=int, default=None,
           help='Seed to use for pseudo-random payload; defaults to clock'))
def GenerateDummy(options):
  print('*** This may be used only to generate a code for testing, '
        'not for a real device.')
  yes_no = input('*** Are you OK with that? (yes/no) ')
  if yes_no != 'yes':
    print('Aborting.')
    sys.exit(1)

  random.seed(options.seed)
  proto = reg_code_pb2.RegCode()
  proto.content.code_type = (reg_code_pb2.UNIQUE_CODE
                             if options.type == 'unique'
                             else reg_code_pb2.GROUP_CODE)

  # Use this weird magic string for the first 16 characters to make it
  # obvious that this is a dummy code.  (Base64-encoding this string
  # results in a reg code that looks like
  # '=CiwKIP______TESTING_______'...)
  proto.content.code = (
      b'\xff\xff\xff\xff\xffLD\x93 \xd1\xbf\xff\xff\xff\xff\xff' + b''.join(
          bytes([random.getrandbits(8)])
          for i in range(
              registration_codes.REGISTRATION_CODE_PAYLOAD_BYTES - 16)))
  proto.content.device = options.project.lower()
  proto.checksum = (
      binascii.crc32(proto.content.SerializeToString()) & 0xFFFFFFFF)

  encoded_string = '=' + base64.urlsafe_b64encode(
      proto.SerializeToString()).strip().decode('utf-8')

  # Make sure the string can be parsed as a sanity check (this will catch,
  # e.g., invalid device names)
  reg_code = RegistrationCode(encoded_string)
  print('')
  print(reg_code.proto)
  print(encoded_string)


@Command(
    'check',
    CmdArg(
        '--unique-code', '-u', metavar='UNIQUE_CODE',
        help=('Unique/user code to check (default: ubind_attribute RW VPD '
              'value)')),
    CmdArg(
        '--group-code', '-g', metavar='GROUP_CODE',
        help='Group code to check (default: gbind_attribute RW VPD value)'),
    CmdArg(
        '--project', '-b', metavar='PROJECT',
        help=('Project to check (default: probed project name if run on DUT; '
              'board name in .default_board if in chroot)')),
    CmdArg(
        '--allow_dummy', action='store_true',
        help='Allow dummy regcode (regcode containing "__TESTING__")'))
def Check(options):
  if not options.project:
    if sys_utils.InChroot():
      options.project = BuildBoard().short_name
    else:
      options.project = hwid_utils.ProbeProject()
  logging.info('Device name: %s', options.project)

  rw_vpd = None
  success = True
  dut = device_utils.CreateDUTInterface()

  for code_type, vpd_attribute, code in (
      (RegistrationCode.Type.UNIQUE_CODE,
       'ubind_attribute', options.unique_code),
      (RegistrationCode.Type.GROUP_CODE,
       'gbind_attribute', options.group_code)):

    if not code:
      if rw_vpd is None:
        if sys_utils.InChroot():
          sys.stderr.write('error: cannot read VPD from chroot; use -u/-g\n')
          sys.exit(1)

        rw_vpd = dut.vpd.rw.GetAll()
      code = rw_vpd.get(vpd_attribute)
      if not code:
        sys.stderr.write('error: %s is not present in RW VPD\n' %
                         vpd_attribute)
        sys.exit(1)

    try:
      registration_codes.CheckRegistrationCode(code, code_type, options.project,
                                               options.allow_dummy)
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
