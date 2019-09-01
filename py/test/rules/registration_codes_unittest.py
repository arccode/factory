#!/usr/bin/env python2
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import base64
import binascii
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.proto import reg_code_pb2
from cros.factory.test.rules.registration_codes import (
    CheckLegacyRegistrationCode)
from cros.factory.test.rules.registration_codes import CheckRegistrationCode
from cros.factory.test.rules.registration_codes import RegistrationCode
from cros.factory.test.rules.registration_codes import RegistrationCodeException


class RegistrationCodeTest(unittest.TestCase):

  def setUp(self):
    # Construct a valid reg code and store it in self.proto.  Other tests
    # may modify the code.
    self.proto = reg_code_pb2.RegCode()
    self.proto.content.code_type = reg_code_pb2.UNIQUE_CODE
    self.proto.content.code = ''.join([chr(x) for x in xrange(32)])
    self.proto.content.device = 'chromebook'

  def _Encode(self, xor_checksum=0):
    """Encodes the reg code in self.proto, returning it as a string.

    Args:
      xor_checksum: A value with which to XOR the checksum.  If this is
          non-zero, the resultant reg code will be (deliberately) invalid.
    """
    self.proto.checksum = (
        binascii.crc32(self.proto.content.SerializeToString())
        & 0xFFFFFFFF) ^ xor_checksum
    return '=' + base64.urlsafe_b64encode(
        self.proto.SerializeToString()).strip()

  def testValid(self):
    # Build and test a valid registration code.
    encoded_string = self._Encode()
    self.assertEquals(
        '=CjAKIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4fEAEaCmNocm9tZWJvb2sQg'
        'dSQ-AI=', self._Encode())

    reg_code = RegistrationCode(encoded_string)
    self.assertEquals('chromebook', reg_code.device)
    self.assertEquals(RegistrationCode.Type.UNIQUE_CODE, reg_code.type)
    self.assertEquals(encoded_string, reg_code.encoded_string)

  def testValid_Pregenerated(self):
    for expected_type, encoded_string in (
        (RegistrationCode.Type.UNIQUE_CODE,
         ('=CioKIKMVpeuuIkf5epYYO5oivYR6HnjFjLg'
          '0ZPbFUuUkMOv2EAEaBGxpbmsQ4PvXgAM=')),
        (RegistrationCode.Type.GROUP_CODE,
         ('=CioKIIG0s3uzLa5cIsxL7P4bNMi-jGzEfiB'
          '8CqFmqOOFVWT4EAAaBGxpbmsQr_PG2gE=')),
        (RegistrationCode.Type.UNIQUE_CODE,
         (u'=CioKIEkzPma0JQrR6gvdlYHzbjp1IN8v1'
          'ybuSPQrindTXip2EAEaBGxpbmsQtKi9uQg=')),
        (RegistrationCode.Type.GROUP_CODE,
         (u'=CioKIIG0s3uzLa5cIsxL7P4bNMi-jGzEf'
          'iB8CqFmqOOFVWT4EAAaBGxpbmsQr_PG2gE=')),
    ):
      reg_code = RegistrationCode(encoded_string)
      self.assertEquals(expected_type, reg_code.type)
      self.assertEquals('link', reg_code.device)

  def testValid_Group(self):
    self.proto.content.code_type = reg_code_pb2.GROUP_CODE
    self.assertEquals(RegistrationCode.Type.GROUP_CODE, RegistrationCode(
        self._Encode()).type)

  def testValid_OneTime(self):
    self.proto.content.code_type = reg_code_pb2.ONE_TIME_CODE
    self.assertEquals(RegistrationCode.Type.ONE_TIME_CODE, RegistrationCode(
        self._Encode()).type)

  def testInvalid_Padding(self):
    # Add some padding.  Code should be invalid.
    self.assertRaisesRegexp(RegistrationCodeException, 'bad base64 encoding',
                            lambda: RegistrationCode(self._Encode() + '='))

  def testInvalid_NonURLSafeBase64(self):
    # Start with a valid code with some '_' and '-' characters.
    valid_code = ('=CjAKIP______TESTING________HI0hPPHdFh'
                  'YHql9BL_zkxEAEaCmNocm9tZWJvb2sQ-vGm-w0=')
    RegistrationCode(valid_code)

    # Make sure that we reject the code if it uses the non-URL-safe
    # encoding.
    invalid_code = '=' + base64.b64encode(base64.urlsafe_b64decode(
        valid_code[1:]))
    self.assertRaisesRegexp(
        RegistrationCodeException, 'bad base64 encoding',
        lambda: RegistrationCode(invalid_code))

  def testInvalid_Not36Chars(self):
    # Remove the first character.  Code should be invalid.
    self.proto.content.code = self.proto.content.code[1:]
    self.assertRaisesRegexp(RegistrationCodeException, 'got 31 bytes',
                            lambda: RegistrationCode(self._Encode()))

  def testInvalid_Checksum(self):
    # Futz with the checksum, invalidating the code.
    self.assertRaisesRegexp(
        RegistrationCodeException, 'expected checksum',
        lambda: RegistrationCode(self._Encode(xor_checksum=1)))

  def testInvalid_NoDevice_Unique(self):
    self.proto.content.ClearField('device')
    self.assertRaisesRegexp(RegistrationCodeException,
                            'expected non-empty device',
                            lambda: RegistrationCode(self._Encode()))

  def testInvalid_NoDevice_Group(self):
    self.proto.content.code_type = reg_code_pb2.GROUP_CODE
    self.proto.content.ClearField('device')
    self.assertRaisesRegexp(RegistrationCodeException,
                            'expected non-empty device',
                            lambda: RegistrationCode(self._Encode()))

  def testValid_OneTimeNoDevice(self):
    self.proto.content.code_type = reg_code_pb2.ONE_TIME_CODE
    self.proto.content.ClearField('device')
    # This time it's OK (one-time code doesn't need a device)
    reg_code = RegistrationCode(self._Encode())
    self.assertIsNone(reg_code.device)

  def testLegacy(self):
    encoded_string = ('000000000000000000000000000000000000'
                      '0000000000000000000000000000190a55ad')
    reg_code = RegistrationCode(encoded_string)
    self.assertIsNone(reg_code.device)
    self.assertEquals(RegistrationCode.Type.LEGACY, reg_code.type)
    self.assertEquals(encoded_string, reg_code.encoded_string)

  def testLegacy_BadChecksum(self):
    encoded_string = ('000000000000000000000000000000000000'
                      '0000000000000000000000000000190a55ae')
    self.assertRaisesRegexp(
        RegistrationCodeException, 'CRC of', RegistrationCode,
        encoded_string)

  def testCheckRegistrationCode(self):
    encoded_string = self._Encode()
    CheckRegistrationCode(encoded_string)
    CheckRegistrationCode(encoded_string,
                          type=RegistrationCode.Type.UNIQUE_CODE)
    CheckRegistrationCode(encoded_string, device='chromebook')
    CheckRegistrationCode(encoded_string,
                          type=RegistrationCode.Type.UNIQUE_CODE,
                          device='chromebook')

    # Wrong type
    self.assertRaisesRegexp(
        RegistrationCodeException,
        "expected type 'GROUP_CODE' but got 'UNIQUE_CODE'",
        CheckRegistrationCode, encoded_string,
        type=RegistrationCode.Type.GROUP_CODE)
    # Wrong device
    self.assertRaisesRegexp(
        RegistrationCodeException,
        "expected device 'foobar' but got 'chromebook'",
        CheckRegistrationCode, encoded_string, device='foobar')

  def testCheckRegistrationCode_Invalid(self):
    self.assertRaisesRegexp(RegistrationCodeException,
                            'Invalid registration code',
                            CheckRegistrationCode, 'abcde')

  def testCheckRegistrationCode_Dummy(self):
    dummy_code = ('=Ci0KIP______TESTING________ijuWNtKM'
                  'IZnagx0HbWaTIEAEaB2Zyb2JiZXIQ3rXp-ws=')
    CheckRegistrationCode(dummy_code, type=RegistrationCode.Type.UNIQUE_CODE,
                          device='frobber', allow_dummy=True)
    self.assertRaisesRegexp(
        RegistrationCodeException, 'is dummy',
        lambda: CheckRegistrationCode(dummy_code,
                                      type=RegistrationCode.Type.UNIQUE_CODE,
                                      device='frobber',
                                      allow_dummy=False))

  def testCheckRegistrationCode_Legacy(self):
    # Types and devices are ignored for legacy codes, since they do
    # not contain type or device fields.
    encoded_string = ('000000000000000000000000000000000000'
                      '0000000000000000000000000000190a55ad')
    CheckRegistrationCode(encoded_string,
                          type=RegistrationCode.Type.UNIQUE_CODE)
    CheckRegistrationCode(encoded_string,
                          type=RegistrationCode.Type.GROUP_CODE)
    CheckRegistrationCode(encoded_string,
                          device='frobber')

  def testCheckLegacyRegistrationCode(self):
    CheckLegacyRegistrationCode('000000000000000000000000000000000000'
                                '0000000000000000000000000000190a55ad')
    CheckLegacyRegistrationCode('010101010101010101010101010101010101'
                                '010101010101010101010101010162319fcc')

    self.assertRaises(
        RegistrationCodeException,
        lambda: CheckLegacyRegistrationCode('00000000'))
    self.assertRaises(
        RegistrationCodeException,
        lambda: CheckLegacyRegistrationCode(
            '000000000000000000000000000000000000'
            '0000000000000000000000000000190a55aD'))  # Uppercase D
    self.assertRaises(
        RegistrationCodeException,
        lambda: CheckLegacyRegistrationCode(
            '000000000000000000000000000000000000'
            '0000000000000000000000000000190a55ae'))  # Bad CRC


if __name__ == '__main__':
  unittest.main()
