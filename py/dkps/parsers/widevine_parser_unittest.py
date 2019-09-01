#!/usr/bin/env python2
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit test for Widevine parser module."""

import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.dkps.parsers import widevine_parser


SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

MOCK_WIDEVINE_FILE_PATH = os.path.join(SCRIPT_DIR, 'testdata', 'widevine.xml')

EXPECTED_PARSED_MOCK_WIDEVINE_KEY_LIST = [
    {'DeviceID': 'device01', 'Key': 'key01', 'ID': 'id01',
     'Magic': 'magic01', 'CRC': 'crc01'},
    {'DeviceID': 'device02', 'Key': 'key02', 'ID': 'id02',
     'Magic': 'magic02', 'CRC': 'crc02'},
    {'DeviceID': 'device03', 'Key': 'key03', 'ID': 'id03',
     'Magic': 'magic03', 'CRC': 'crc03'}]


class WidevineParserTest(unittest.TestCase):
  def runTest(self):
    with open(MOCK_WIDEVINE_FILE_PATH) as f:
      self.assertEqual(EXPECTED_PARSED_MOCK_WIDEVINE_KEY_LIST,
                       widevine_parser.Parse(f.read()))


if __name__ == '__main__':
  unittest.main()
