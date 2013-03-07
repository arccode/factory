#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common # pylint: disable=W0611
import os
import unittest

from cros.factory.hwid import Database
from cros.factory.hwid.decoder import EncodedStringToBinaryString
from cros.factory.hwid.decoder import BinaryStringToBOM, Decode

_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


class DecoderTest(unittest.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(os.path.join(_TEST_DATA_PATH,
                                                   'test_db.yaml'))
    self.expected_components_from_db = {
        'audio_codec': ['Codec 1', 'HDMI 1'],
        'battery': ['Battery Li-ion 10000000'],
        'bluetooth': ['0123:abcd 0001'],
        'camera': ['4567:abcd Camera'],
        'chipset': ['cdef:abcd'],
        'cpu': ['CPU @ 2.80GHz [4 cores]'],
        'display_panel': ['FOO:0123 [1440x900]'],
        'dram': ['0|2048|DDR3-800,DDR3-1066,DDR3-1333,DDR3-1600 1|2048|DDR3-800'
            ',DDR3-1066,DDR3-1333,DDR3-1600'],
        'ec_flash_chip': ['EC Flash Chip'],
        'embedded_controller': ['Embedded Controller'],
        'flash_chip': ['Flash Chip'],
        'keyboard': ['xkb:us::eng'],
        'storage': ['16G SSD #123456'],
        'touchpad': ['TouchPad'],
        'tpm': ['12340000:1.2.3'],
        'usb_hosts': ['8086:0000', '8086:0001'],
        'vga': ['8086:0002'],
        'wireless': ['3210:abcd'],
        'hash_gbb': ['gv2#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
            'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'],
        'key_recovery': ['kv3#bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'],
        'key_root': ['kv3#cccccccccccccccccccccccccccccccccccccccc'],
        'ro_ec_firmware': ['ev2#dddddddddddddddddddddddddddddddddddd'
            'dddddddddddddddddddddddddddd#chromebook'],
        'ro_main_firmware': ['mv2#eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
            'eeeeeeeeeeeeeeeeeeeeeeeeeeeeee#chromebook'],
        'cellular': None}

  def testEncodedStringToBinaryString(self):
    self.assertEquals('00000111010000010100',
                      EncodedStringToBinaryString(
                          self.database, 'CHROMEBOOK A5AU-LU'))

  def testBinaryStringToBOM(self):
    result = open(os.path.join(_TEST_DATA_PATH,
                               'test_probe_result.yaml'), 'r').read()
    reference_bom = self.database.ProbeResultToBOM(result)
    bom = BinaryStringToBOM(self.database, '00000111010000010100')
    self.assertEquals(reference_bom.board, bom.board)
    self.assertEquals(reference_bom.encoding_pattern_index,
                      bom.encoding_pattern_index)
    self.assertEquals(reference_bom.image_id, bom.image_id)
    self.assertEquals(reference_bom.encoded_fields, bom.encoded_fields)
    self.assertEquals(self.expected_components_from_db, bom.components)

  def testDecode(self):
    result = open(os.path.join(_TEST_DATA_PATH,
                               'test_probe_result.yaml'), 'r').read()
    reference_bom = self.database.ProbeResultToBOM(result)
    hwid = Decode(self.database, 'CHROMEBOOK A5AU-LU')
    self.assertEquals('00000111010000010100', hwid.binary_string)
    self.assertEquals('CHROMEBOOK A5AU-LU', hwid.encoded_string)
    self.assertEquals(reference_bom.board, hwid.bom.board)
    self.assertEquals(reference_bom.encoding_pattern_index,
                      hwid.bom.encoding_pattern_index)
    self.assertEquals(reference_bom.image_id, hwid.bom.image_id)
    self.assertEquals(reference_bom.encoded_fields, hwid.bom.encoded_fields)
    self.assertEquals(self.expected_components_from_db, hwid.bom.components)


if __name__ == '__main__':
  unittest.main()
