#!/usr/bin/env python2
#
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire.server import webapp_utils


class ParseDUTHeaderTest(unittest.TestCase):

  def testSingleKeyValue(self):
    self.assertDictEqual(
        {'sn': 'SN001'},
        webapp_utils.ParseDUTHeader('sn=SN001'))
    self.assertDictEqual(
        {'mlb_sn': 'MLB001'},
        webapp_utils.ParseDUTHeader('mlb_sn=MLB001'))
    self.assertDictEqual(
        {'firmware': 'spring_1.0.1'},
        webapp_utils.ParseDUTHeader('firmware=spring_1.0.1'))
    self.assertDictEqual(
        {'ec': 'spring_ec_1.0.1'},
        webapp_utils.ParseDUTHeader('ec=spring_ec_1.0.1'))

  def testSingleKeyPrefixValue(self):
    self.assertDictEqual(
        {'mac': 'aa:bb:cc:dd:ee:ff'},
        webapp_utils.ParseDUTHeader('mac=aa:bb:cc:dd:ee:ff'))
    self.assertDictEqual(
        {'mac.eth0': 'aa:bb:cc:dd:ee:ff'},
        webapp_utils.ParseDUTHeader('mac.eth0=aa:bb:cc:dd:ee:ff'))
    self.assertDictEqual(
        {'mac.wlan0': 'aa:bb:cc:dd:ee:ff'},
        webapp_utils.ParseDUTHeader('mac.wlan0=aa:bb:cc:dd:ee:ff'))

  def testMultipleValues(self):
    self.assertDictEqual(
        {'mac': 'aa:bb:cc:dd:ee:ff', 'sn': 'SN001', 'mlb_sn': 'MLB001'},
        webapp_utils.ParseDUTHeader(
            'mac=aa:bb:cc:dd:ee:ff; sn=SN001; mlb_sn=MLB001'))

  def testInvalidKey(self):
    with self.assertRaises(ValueError):
      webapp_utils.ParseDUTHeader('invalid_key=value')

  def testLegacyKey(self):
    self.assertDictEqual({}, webapp_utils.ParseDUTHeader('board=eve'))

if __name__ == '__main__':
  unittest.main()
