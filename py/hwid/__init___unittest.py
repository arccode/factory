#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=W0212

import factory_common # pylint: disable=W0611
import os
import unittest2

from cros.factory.hwid import HWIDException, Database, MakeList, MakeSet
from cros.factory.hwid.encoder import Encode

_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'test_data')


class HWIDTest(unittest2.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(os.path.join(_TEST_DATA_PATH,
                                                   'test_db.yaml'))

  def testMakeList(self):
    self.assertEquals(['a'], MakeList('a'))
    self.assertEquals(['abc'], MakeList('abc'))
    self.assertEquals(['a', 'b'], MakeList(['a', 'b']))
    self.assertEquals(['a', 'b'], MakeList({'a': 'foo', 'b': 'bar'}))

  def testMakeSet(self):
    self.assertEquals(set(['ab']), MakeSet('ab'))
    self.assertEquals(set(['a', 'b']), MakeSet(['a', 'b']))
    self.assertEquals(set(['a', 'b']), MakeSet(('a', 'b')))
    self.assertEquals(set(['a', 'b']), MakeSet({'a': 'foo', 'b': 'bar'}))

  def testVerify(self):
    result = open(os.path.join(_TEST_DATA_PATH,
                               'test_probe_result.yaml'), 'r').read()
    bom = self.database.ProbeResultToBOM(result)
    hwid = Encode(self.database, bom)
    self.assertTrue(hwid.Verify())

    # The correct binary string: '00000111010000010100'
    original_value = hwid.binary_string
    hwid.binary_string = '000001110100000101100'
    self.assertRaisesRegexp(
        HWIDException, r'Invalid bit string length', hwid.Verify)
    hwid.binary_string = '00000011010000010100'
    self.assertRaisesRegexp(
        HWIDException, r'Binary string .* does not encode to encoded string .*',
        hwid.Verify)
    hwid.binary_string = original_value

    original_value = hwid.encoded_string
    hwid.encoded_string = 'ASDF QWER-TY'
    self.assertRaisesRegexp(
        HWIDException, r'Invalid board name', hwid.Verify)
    hwid.encoded_string = original_value

    original_value = hwid.bom
    hwid.bom.encoded_fields['cpu'] = 10
    self.assertRaisesRegexp(
        HWIDException, r'Encoded fields .* have unknown indices',
        hwid.Verify)
    hwid.bom.encoded_fields['cpu'] = 2
    self.assertRaisesRegexp(
        HWIDException, r'BOM does not encode to binary string .*', hwid.Verify)
    hwid.bom = original_value

class DatabaseTest(unittest2.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(os.path.join(_TEST_DATA_PATH,
                                                   'test_db.yaml'))
  def testProbeResultToBOM(self):
    result = open(os.path.join(_TEST_DATA_PATH,
                               'test_probe_result.yaml'), 'r').read()
    bom = self.database.ProbeResultToBOM(result)
    self.assertEquals('CHROMEBOOK', bom.board)
    self.assertEquals(0, bom.encoding_pattern_index)
    self.assertEquals(0, bom.image_id)
    self.assertEquals({
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
        'cellular_fw_version': [''],
        'rw_fw_key_version': ['2'],
        'storage_fw_version': ['11.22.33'],
        'wimax': None,
        'cellular': None,
        'display_converter': None,
        'ethernet': None}, bom.components)
    self.assertEquals({
        'audio_codec': 1,
        'battery': 3,
        'bluetooth': 0,
        'camera': 0,
        'cellular': 0,
        'chipset': 0,
        'cpu': 5,
        'display_panel': 0,
        'dram': 0,
        'ec_flash_chip': 0,
        'embedded_controller': 0,
        'firmware': 0,
        'flash_chip': 0,
        'keyboard': 0,
        'storage': 0,
        'touchpad': 0,
        'tpm': 0,
        'usb_hosts': 0,
        'vga': 0,
        'wireless': 0}, bom.encoded_fields)
    result = result.replace('chipset: cdef:abcd', 'chipset: something else')
    self.assertRaisesRegexp(
        HWIDException, r'Cannot find matching encoded index for .* from the '
        'probe result', self.database.ProbeResultToBOM, result)

  def testGetFieldIndexFromComponents(self):
    result = open(os.path.join(_TEST_DATA_PATH,
                               'test_probe_result.yaml'), 'r').read()
    bom = self.database.ProbeResultToBOM(result)
    self.assertEquals(5, self.database._GetFieldIndexFromComponents(
        'cpu', bom.components))
    self.assertEquals(1, self.database._GetFieldIndexFromComponents(
        'audio_codec', bom.components))
    self.assertEquals(3, self.database._GetFieldIndexFromComponents(
        'battery', bom.components))
    self.assertEquals(0, self.database._GetFieldIndexFromComponents(
        'storage', bom.components))
    self.assertEquals(0, self.database._GetFieldIndexFromComponents(
        'cellular', bom.components))
    self.assertEquals(None, self.database._GetFieldIndexFromComponents(
        'wimax', bom.components))

  def testGetAllIndices(self):
    self.assertEquals([0, 1, 2, 3, 4, 5], self.database._GetAllIndices('cpu'))
    self.assertEquals([0, 1], self.database._GetAllIndices('dram'))
    self.assertEquals([0], self.database._GetAllIndices('wireless'))

  def testGetAttributesByIndex(self):
    self.assertEquals({'battery': [{
                          'name': 'battery_large',
                          'value': 'Battery Li-ion 7500000'}]},
                      self.database._GetAttributesByIndex('battery', 2))
    self.assertEquals(
        {'hash_gbb': [{
              'name': 'hash_gbb_0',
              'value': 'gv2#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
                       'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}],
         'key_recovery': [{
              'name': 'key_recovery_0',
              'value': 'kv3#bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'}],
         'key_root': [{
              'name': 'key_root_0',
              'value': 'kv3#cccccccccccccccccccccccccccccccccccccccc'}],
         'ro_ec_firmware': [{
              'name': 'ro_ec_firmware_0',
              'value': 'ev2#ddddddddddddddddddddddddddddddddddd'
                       'ddddddddddddddddddddddddddddd#chromebook'}],
         'ro_main_firmware': [{
              'name': 'ro_main_firmware_0',
              'value': 'mv2#eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
                       'eeeeeeeeeeeeeeeeeeeeeeeeeeeee#chromebook'}]},
        self.database._GetAttributesByIndex('firmware', 0))
    self.assertEquals({
        'audio_codec': [
          {'name': 'codec_0', 'value': 'Codec 0'},
          {'name': 'hdmi_0', 'value': 'HDMI 0'}]},
        self.database._GetAttributesByIndex('audio_codec', 0))
    self.assertEquals({'cellular': None},
                      self.database._GetAttributesByIndex('cellular', 0))

  def testVerifyBinaryString(self):
    self.assertTrue(self.database.VerifyBinaryString('00000101001101101100'))
    self.assertRaisesRegexp(
        HWIDException, r'Invalid binary string: .*',
        self.database.VerifyBinaryString, '020001010011011011000')
    self.assertRaisesRegexp(
        HWIDException, r'Binary string .* does not have stop bit set',
        self.database.VerifyBinaryString, '00000')
    self.assertRaisesRegexp(
        HWIDException, r'Invalid bit string length',
        self.database.VerifyBinaryString, '0000010100110110111000')

  def testVerifyEncodedString(self):
    self.assertEquals(
        True, self.database.VerifyEncodedString('CHROMEBOOK AW3L-M7I7-V'))
    self.assertRaisesRegexp(
        HWIDException, r'Invalid HWID string format',
        self.database.VerifyEncodedString, 'AW3L-M7I5-4')
    self.assertRaisesRegexp(
        HWIDException, r'Length of encoded string .* is less than 2 characters',
        self.database.VerifyEncodedString, 'FOO A')
    self.assertRaisesRegexp(
        HWIDException, r'Invalid board name', self.database.VerifyEncodedString,
        'FOO AW3L-M7IK-W')
    self.assertRaisesRegexp(
        HWIDException, r'Checksum of .* mismatch',
        self.database.VerifyEncodedString, 'CHROMEBOOK AW3L-M7IA-B')

  def testVerifyBOM(self):
    result = open(os.path.join(_TEST_DATA_PATH,
                               'test_probe_result.yaml'), 'r').read()
    bom = self.database.ProbeResultToBOM(result)
    self.assertTrue(self.database.VerifyBOM(bom))

    original_value = bom.components['ec_flash_chip']
    bom.components.pop('ec_flash_chip')
    self.assertRaisesRegexp(
        HWIDException, r'Missing component classes: .*',
        self.database.VerifyBOM, bom)
    bom.components['ec_flash_chip'] = original_value

    original_value = bom.board
    bom.board = 'FOO'
    self.assertRaisesRegexp(
        HWIDException, r'Invalid board name. Expected .*, got .*',
        self.database.VerifyBOM, bom)
    bom.board = original_value

    original_value = bom.encoding_pattern_index
    bom.encoding_pattern_index = 1
    self.assertRaisesRegexp(
        HWIDException, r'Invalid encoding pattern', self.database.VerifyBOM,
        bom)
    bom.encoding_pattern_index = original_value

    original_value = bom.image_id
    bom.image_id = 5
    self.assertRaisesRegexp(
        HWIDException, r'Invalid image id: .*', self.database.VerifyBOM, bom)
    bom.image_id = original_value

    original_value = bom.encoded_fields['cpu']
    bom.encoded_fields['cpu'] = 8
    self.assertRaisesRegexp(
        HWIDException, r'Encoded fields .* have unknown indices',
        self.database.VerifyBOM, bom)
    bom.encoded_fields['cpu'] = original_value

    bom.encoded_fields['foo'] = 1
    self.assertRaisesRegexp(
        HWIDException, r'Extra encoded fields in BOM: .*',
        self.database.VerifyBOM, bom)
    bom.encoded_fields.pop('foo')

    original_value = bom.components['cpu']
    bom.components['cpu'] = 'foo'
    self.assertRaisesRegexp(
        HWIDException, r'Unknown component values: .*', self.database.VerifyBOM,
        bom)
    bom.components['cpu'] = original_value

    original_value = bom.encoded_fields['cpu']
    bom.encoded_fields.pop('cpu')
    self.assertRaisesRegexp(
        HWIDException, r'Missing encoded fields in BOM: .*',
        self.database.VerifyBOM, bom)
    bom.encoded_fields['cpu'] = original_value


class PatternTest(unittest2.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(os.path.join(_TEST_DATA_PATH,
                                                   'test_db.yaml'))
    self.pattern = self.database.pattern

  def testGetFieldsBitLength(self):
    length = self.pattern.GetFieldsBitLength()
    self.assertEquals(1, length['audio_codec'])
    self.assertEquals(2, length['battery'])
    self.assertEquals(0, length['bluetooth'])
    self.assertEquals(0, length['camera'])
    self.assertEquals(1, length['cellular'])
    self.assertEquals(0, length['chipset'])
    self.assertEquals(3, length['cpu'])
    self.assertEquals(0, length['display_panel'])
    self.assertEquals(1, length['dram'])
    self.assertEquals(0, length['ec_flash_chip'])
    self.assertEquals(0, length['embedded_controller'])
    self.assertEquals(0, length['flash_chip'])
    self.assertEquals(1, length['keyboard'])
    self.assertEquals(2, length['storage'])
    self.assertEquals(0, length['touchpad'])
    self.assertEquals(0, length['tpm'])
    self.assertEquals(0, length['usb_hosts'])
    self.assertEquals(0, length['vga'])
    self.assertEquals(0, length['wireless'])
    self.assertEquals(1, length['firmware'])

    original_value = self.pattern.pattern
    self.pattern.pattern = None
    self.assertRaisesRegexp(
        HWIDException, r'Cannot get encoded field bit length with uninitialized'
        ' pattern', self.pattern.GetFieldsBitLength)
    self.pattern.pattern = original_value

  def testGetTotalBitLength(self):
    length = self.database.pattern.GetTotalBitLength()
    self.assertEquals(18, length)

    original_value = self.pattern.pattern
    self.pattern.pattern = None
    self.assertRaisesRegexp(
        HWIDException, r'Cannot get bit length with uninitialized pattern',
        self.pattern.GetTotalBitLength)
    self.pattern.pattern = original_value

  def testGetBitMapping(self):
    mapping = self.pattern.GetBitMapping()
    self.assertEquals('audio_codec', mapping[5].field)
    self.assertEquals(0, mapping[5].bit_offset)
    self.assertEquals('battery', mapping[6].field)
    self.assertEquals(0, mapping[6].bit_offset)
    self.assertEquals('battery', mapping[7].field)
    self.assertEquals(1, mapping[7].bit_offset)
    self.assertEquals('cellular', mapping[8].field)
    self.assertEquals(0, mapping[8].bit_offset)
    self.assertEquals('cpu', mapping[9].field)
    self.assertEquals(0, mapping[9].bit_offset)
    self.assertEquals('cpu', mapping[12].field)
    self.assertEquals(1, mapping[12].bit_offset)
    self.assertEquals('storage', mapping[13].field)
    self.assertEquals(0, mapping[13].bit_offset)
    self.assertEquals('storage', mapping[14].field)
    self.assertEquals(1, mapping[14].bit_offset)
    self.assertEquals('cpu', mapping[15].field)
    self.assertEquals(2, mapping[15].bit_offset)
    self.assertEquals('firmware', mapping[16].field)
    self.assertEquals(0, mapping[16].bit_offset)

    original_value = self.pattern.pattern
    self.pattern.pattern = None
    self.assertRaisesRegexp(
        HWIDException, r'Cannot construct bit mapping with uninitialized '
        'pattern', self.pattern.GetBitMapping)
    self.pattern.pattern = original_value

if __name__ == '__main__':
  unittest2.main()
