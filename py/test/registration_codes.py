#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import binascii
import re
import struct


def CheckRegistrationCode(code):
  '''Checks that a registration code is valid, raising a ValueError if not.'''
  if len(code) != 72:
    raise ValueError('Registration code %r is not 72 characters long' % code)
  if re.search('[^0-9a-f]', code):
    raise ValueError('Registration code %r has invalid characters' % code)

  # Parse payload and CRC as byte strings.
  payload = binascii.unhexlify(code[0:64])
  crc = binascii.unhexlify(code[64:72])
  expected_crc = struct.pack('!I', binascii.crc32(payload) & 0xFFFFFFFF)
  if expected_crc != crc:
    raise ValueError('CRC of %r is invalid (should be %s)' %
                     (code, binascii.hexlify(expected_crc)))

