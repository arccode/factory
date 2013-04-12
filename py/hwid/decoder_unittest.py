#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest2
import yaml
import factory_common # pylint: disable=W0611

from cros.factory.hwid import Database, HWIDException, DEFAULT_HWID_DATA_PATH
from cros.factory.hwid.decoder import EncodedStringToBinaryString
from cros.factory.hwid.decoder import BinaryStringToBOM, Decode

_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


class DecoderTest(unittest2.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(os.path.join(_TEST_DATA_PATH,
                                                   'test_db.yaml'))
    self.results = [
        yaml.dump(result) for result in yaml.load_all(open(os.path.join(
            _TEST_DATA_PATH, 'test_probe_result.yaml')).read())]
    self.expected_components_from_db = {
       'audio_codec': [('codec_1', 'Codec 1', None),
                       ('hdmi_1', 'HDMI 1', None)],
       'battery': [('battery_huge', 'Battery Li-ion 10000000', None)],
       'bluetooth': [('bluetooth_0', '0123:abcd 0001', None)],
       'camera': [('camera_0', '4567:abcd Camera', None)],
       'cellular': [(None, None, "Missing 'cellular' component")],
       'chipset': [('chipset_0', 'cdef:abcd', None)],
       'cpu': [('cpu_5', 'CPU @ 2.80GHz [4 cores]', None)],
       'display_panel': [('display_panel_0', 'FOO:0123 [1440x900]', None)],
       'dram': [('dram_0', 'DRAM 4G', None)],
       'ec_flash_chip': [('ec_flash_chip_0', 'EC Flash Chip', None)],
       'embedded_controller': [('embedded_controller_0', 'Embedded Controller',
                               None)],
       'flash_chip': [('flash_chip_0', 'Flash Chip', None)],
       'hash_gbb': [('hash_gbb_0', 'gv2#hash_gbb_0', None)],
       'key_recovery': [('key_recovery_0', 'kv3#key_recovery_0', None)],
       'key_root': [('key_root_0', 'kv3#key_root_0', None)],
       'keyboard': [('keyboard_us', 'xkb:us::eng', None)],
       'ro_ec_firmware': [('ro_ec_firmware_0', 'ev2#ro_ec_firmware_0', None)],
       'ro_main_firmware': [
            ('ro_main_firmware_0', 'mv2#ro_main_firmware_0', None)],
       'storage': [('storage_0', '16G SSD #123456', None)]}

  def testEncodedStringToBinaryString(self):
    self.assertEquals('0000000000111010000011000',
                      EncodedStringToBinaryString(
                          self.database, 'CHROMEBOOK AA5A-Y6L'))
    self.assertEquals('0010100000111010000011000',
                      EncodedStringToBinaryString(
                          self.database, 'CHROMEBOOK FA5A-Y63'))
    self.assertEquals('1000000000111010000011000',
                      EncodedStringToBinaryString(
                          self.database, 'CHROMEBOOK QA5A-YCJ'))

  def testBinaryStringToBOM(self):
    reference_bom = self.database.ProbeResultToBOM(self.results[0])
    reference_bom = self.database.UpdateComponentsOfBOM(reference_bom, {
        'keyboard': 'keyboard_us', 'dram': 'dram_0',
        'display_panel': 'display_panel_0'})
    bom = BinaryStringToBOM(self.database, '0000000000111010000011000')
    self.assertEquals(reference_bom.board, bom.board)
    self.assertEquals(reference_bom.encoding_pattern_index,
                      bom.encoding_pattern_index)
    self.assertEquals(reference_bom.image_id, bom.image_id)
    self.assertEquals(reference_bom.encoded_fields, bom.encoded_fields)
    self.assertEquals(self.expected_components_from_db, bom.components)
    bom = BinaryStringToBOM(self.database, '0000000001111010000011000')
    self.assertEquals(1, bom.encoded_fields['firmware'])
    self.assertEquals(5, BinaryStringToBOM(
        self.database, '0010100000111010000011000').image_id)
    self.assertEquals(1, BinaryStringToBOM(
        self.database, '1000000000111010000011000').encoding_pattern_index)
    self.assertRaisesRegexp(
        HWIDException, r"Invalid encoded field index: {'cpu': 6}",
        BinaryStringToBOM, self.database, '0000000000111000010011000')

  def testDecode(self):
    reference_bom = self.database.ProbeResultToBOM(self.results[0])
    reference_bom = self.database.UpdateComponentsOfBOM(reference_bom, {
        'keyboard': 'keyboard_us', 'dram': 'dram_0',
        'display_panel': 'display_panel_0'})
    hwid = Decode(self.database, 'CHROMEBOOK AA5A-Y6L')
    self.assertEquals('0000000000111010000011000', hwid.binary_string)
    self.assertEquals('CHROMEBOOK AA5A-Y6L', hwid.encoded_string)
    self.assertEquals(reference_bom.board, hwid.bom.board)
    self.assertEquals(reference_bom.encoding_pattern_index,
                      hwid.bom.encoding_pattern_index)
    self.assertEquals(reference_bom.image_id, hwid.bom.image_id)
    self.assertEquals(reference_bom.encoded_fields, hwid.bom.encoded_fields)
    self.assertEquals(self.expected_components_from_db, hwid.bom.components)

  def testPreviousVersionOfEncodedString(self):
    bom = BinaryStringToBOM(self.database, '0000000000111010000010000')
    self.assertEquals(1, bom.encoded_fields['cpu'])
    hwid = Decode(self.database, 'CHROMEBOOK AA5A-Q7Z')
    self.assertEquals('0000000000111010000010000', hwid.binary_string)
    self.assertEquals('CHROMEBOOK AA5A-Q7Z', hwid.encoded_string)
    self.assertEquals(1, hwid.bom.encoded_fields['cpu'])

  def testDecodeSpringEVT(self):
    database = Database.LoadFile(os.path.join(DEFAULT_HWID_DATA_PATH, 'SPRING'))
    hwid = Decode(database, 'SPRING AAAD-TB2')
    self.assertEquals({
        'keyboard_field': 0,
        'firmware_field': 0,
        'antenna_field': 0,
        'audio_codec_field': 0,
        'battery_field': 0,
        'bluetooth_field': 0,
        'camera_field': 0,
        'cellular_field': 1,
        'chipset_field': 0,
        'cpu_field': 0,
        'display_panel_field': 0,
        'dram_field': 1,
        'embedded_controller_field': 0,
        'flash_chip_field': 1,
        'pcb_vendor_field': 0,
        'pmic_field': 0,
        'storage_field': 1,
        'touchpad_field': 0,
        'tpm_field': 0,
        'usb_hosts_field': 0,
        'wireless_field': 0,
        }, hwid.bom.encoded_fields)
    hwid = Decode(database, 'SPRING AQAD-T5F')
    self.assertEquals({
        'keyboard_field': 1,
        'firmware_field': 0,
        'antenna_field': 0,
        'audio_codec_field': 0,
        'battery_field': 0,
        'bluetooth_field': 0,
        'camera_field': 0,
        'cellular_field': 1,
        'chipset_field': 0,
        'cpu_field': 0,
        'display_panel_field': 0,
        'dram_field': 1,
        'embedded_controller_field': 0,
        'flash_chip_field': 1,
        'pcb_vendor_field': 0,
        'pmic_field': 0,
        'storage_field': 1,
        'touchpad_field': 0,
        'tpm_field': 0,
        'usb_hosts_field': 0,
        'wireless_field': 0,
        }, hwid.bom.encoded_fields)


if __name__ == '__main__':
  unittest2.main()
