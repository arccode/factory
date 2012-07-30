#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.registration_codes import CheckRegistrationCode


class RegistrationCodeTest(unittest.TestCase):
  def runTest(self):
    CheckRegistrationCode('000000000000000000000000000000000000'
                          '0000000000000000000000000000190a55ad')
    CheckRegistrationCode('010101010101010101010101010101010101'
                          '010101010101010101010101010162319fcc')

    self.assertRaises(
        ValueError,
        lambda: CheckRegistrationCode('00000000'))
    self.assertRaises(
        ValueError,
        lambda: CheckRegistrationCode(
            '000000000000000000000000000000000000'
            '0000000000000000000000000000190a55aD'))  # Uppercase D
    self.assertRaises(
        ValueError,
        lambda: CheckRegistrationCode(
            '000000000000000000000000000000000000'
            '0000000000000000000000000000190a55ae'))  # Bad CRC


if __name__ == '__main__':
  unittest.main()
