#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest
import yaml
import factory_common  # pylint: disable=W0611

from cros.factory.hwid.v3.common import HWIDException
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3.decoder import EncodedStringToBinaryString
from cros.factory.hwid.v3.decoder import BinaryStringToBOM, Decode
from cros.factory.hwid.v3.rule import Value

_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


class DecoderTest(unittest.TestCase):

  def setUp(self):
    self.database = Database.LoadFile(os.path.join(_TEST_DATA_PATH,
                                                   'test_db.yaml'))
    self.results = [
        yaml.dump(result) for result in yaml.load_all(open(os.path.join(
            _TEST_DATA_PATH, 'test_probe_result.yaml')).read())]
    self.expected_components_from_db = {
        'audio_codec': [('codec_1', {'compact_str': Value('Codec 1')}, None),
                        ('hdmi_1', {'compact_str': Value('HDMI 1')}, None)],
        'battery': [('battery_huge',
                     {'tech': Value('Battery Li-ion'),
                      'size': Value('10000000')},
                     None)],
        'bluetooth': [('bluetooth_0',
                       {'idVendor': Value('0123'), 'idProduct': Value('abcd'),
                        'bcd': Value('0001')},
                       None)],
        'cellular': [(None, None, "Missing 'cellular' component")],
        'cpu': [('cpu_5',
                 {'name': Value('CPU @ 2.80GHz'), 'cores': Value('4')},
                 None)],
        'display_panel': [('display_panel_0', None, None)],
        'dram': [('dram_0',
                  {'vendor': Value('DRAM 0'), 'size': Value('4G')},
                  None)],
        'ec_flash_chip': [('ec_flash_chip_0',
                           {'compact_str': Value('EC Flash Chip')},
                           None)],
        'embedded_controller': [('embedded_controller_0',
                                 {'compact_str': Value('Embedded Controller')},
                                 None)],
        'flash_chip': [('flash_chip_0',
                        {'compact_str': Value('Flash Chip')},
                        None)],
        'hash_gbb': [('hash_gbb_0',
                      {'compact_str': Value('gv2#hash_gbb_0')},
                      None)],
        'key_recovery': [('key_recovery_0',
                          {'compact_str': Value('kv3#key_recovery_0')},
                          None)],
        'key_root': [('key_root_0',
                      {'compact_str': Value('kv3#key_root_0')},
                      None)],
        'keyboard': [('keyboard_us', None, None)],
        'ro_ec_firmware': [('ro_ec_firmware_0',
                            {'compact_str': Value('ev2#ro_ec_firmware_0')},
                            None)],
        'ro_main_firmware': [('ro_main_firmware_0',
                              {'compact_str': Value('mv2#ro_main_firmware_0')},
                              None)],
        'storage': [('storage_0',
                     {'type': Value('SSD'), 'size': Value('16G'),
                      'serial': Value(r'^#123\d+$', is_re=True)},
                     None)],
        'video': [('camera_0',
                   {'idVendor': Value('4567'), 'idProduct': Value('abcd'),
                    'type': Value('webcam')},
                   None)]}

  def _CheckBOM(self, reference_bom, bom):
    """Check the BOM decoded from HWID is equivalent to the reference BOM.

    reference_bom (generated from probed result) has all information of
    encoded_fields and component, but bom (generated from binary string) only
    has the information of the pattern. Therefore we check bom is the subset
    of the reference_bom.
    """
    self.assertEquals(reference_bom.board, bom.board)
    self.assertEquals(reference_bom.encoding_pattern_index,
                      bom.encoding_pattern_index)
    self.assertEquals(reference_bom.image_id, bom.image_id)
    for comp_cls in bom.encoded_fields:
      self.assertEquals(reference_bom.encoded_fields[comp_cls],
                        bom.encoded_fields[comp_cls])
    for comp_cls in bom.components:
      self.assertEquals(self.expected_components_from_db[comp_cls],
                        bom.components[comp_cls])

  def testEncodedStringToBinaryString(self):
    self.assertEquals('0000000000111010000011',
                      EncodedStringToBinaryString(
                          self.database, 'CHROMEBOOK AA5A-Y6L'))
    self.assertEquals('0001000000111010000011',
                      EncodedStringToBinaryString(
                          self.database, 'CHROMEBOOK C2H-I3Q-A6Q'))
    self.assertEquals('1000000000111010000011',
                      EncodedStringToBinaryString(
                          self.database, 'CHROMEBOOK QA5A-YCJ'))

  def testBinaryStringToBOM(self):
    reference_bom = self.database.ProbeResultToBOM(self.results[0])
    reference_bom = self.database.UpdateComponentsOfBOM(reference_bom, {
        'keyboard': 'keyboard_us',
        'display_panel': 'display_panel_0'})
    bom = BinaryStringToBOM(self.database, '0000000000111010000011')
    self._CheckBOM(reference_bom, bom)

    bom = BinaryStringToBOM(self.database, '0000000001111010000011')
    self.assertEquals(1, bom.encoded_fields['firmware'])
    self.assertEquals(2, BinaryStringToBOM(
        self.database, '0001000000111010000011').image_id)
    self.assertEquals(1, BinaryStringToBOM(
        self.database, '1000000000111010000011').encoding_pattern_index)
    self.assertRaisesRegexp(
        HWIDException, r"Invalid encoded field index: {'cpu': 6}",
        BinaryStringToBOM, self.database, '0000000000111000010011')

  def testIncompleteBinaryStringToBOM(self):
    # The latest pattern in the test database has 16 bits (plus the image ID and
    # the stop bit), with the last three bits being one two-bit storage_field,
    # and one one-bit cpu_field.

    # Test with 21 bits here. This should be regarded as a valid binary string
    # that was generated before we extended cpu_field.
    bom = BinaryStringToBOM(
        self.database,
        '00000'         # image ID
        '0000111101000'  # 13 bits, up through second cpu_field
        '00'            # storage_field
        '1')            # stop bit
    # Bit 15 is 1, which is the first cpu_field. The cpu_field should be decoded
    # as b01 = 1.
    self.assertEquals(1, bom.encoded_fields['cpu'])
    self.assertEquals(0, bom.encoded_fields['storage'])

    # Test with 20 bits here. This should be regarded as an incomplete bit chunk
    # for storage_field, i.e. storage_field was previously one bit (and some
    # HWIDs were generated) but it has since been extended to two bits.
    bom = BinaryStringToBOM(
        self.database,
        '00000'         # image ID
        '0000111101000'  # 12 bits, up through second cpu_field
        '1'             # the incomplete storage_field chunk
        '1')            # stop bit
    # The cpu_field should still be b01 = 1.
    self.assertEquals(1, bom.encoded_fields['cpu'])
    # The 1 in the incomplete two-bit storage field should be decoded as b1 = 1
    # instead of b10 = 2.
    self.assertEquals(1, bom.encoded_fields['storage'])

  def testDecode(self):
    reference_bom = self.database.ProbeResultToBOM(self.results[0])
    reference_bom = self.database.UpdateComponentsOfBOM(reference_bom, {
        'keyboard': 'keyboard_us', 'dram': 'dram_0',
        'display_panel': 'display_panel_0'})
    hwid = Decode(self.database, 'CHROMEBOOK AA5A-Y6L')
    self.assertEquals('0000000000111010000011', hwid.binary_string)
    self.assertEquals('CHROMEBOOK AA5A-Y6L', hwid.encoded_string)
    self._CheckBOM(reference_bom, hwid.bom)

    hwid = Decode(self.database, 'CHROMEBOOK C2H-I3Q-A6Q')
    self.assertEquals('0001000000111010000011', hwid.binary_string)
    self.assertEquals('CHROMEBOOK C2H-I3Q-A6Q', hwid.encoded_string)
    reference_bom.image_id = 2
    self._CheckBOM(reference_bom, hwid.bom)

  def testPreviousVersionOfEncodedString(self):
    bom = BinaryStringToBOM(self.database, '000000000011101000001')
    self.assertEquals(1, bom.encoded_fields['cpu'])
    hwid = Decode(self.database, 'CHROMEBOOK AA5A-Q7Z')
    self.assertEquals('000000000011101000001', hwid.binary_string)
    self.assertEquals('CHROMEBOOK AA5A-Q7Z', hwid.encoded_string)
    self.assertEquals(1, hwid.bom.encoded_fields['cpu'])

  def testDecodeRegion(self):
    db = Database.LoadFile(
        os.path.join(_TEST_DATA_PATH, 'test_db_regions.yaml'))
    hwid = Decode(db, 'CHROMEBOOK A25-Q22')
    # The BOM should load 'us' region from the probe result (numeric_id=29).)
    self.assertEquals(29, hwid.bom.encoded_fields['region_field'])
    self.assertEquals(
        [('us', {'region_code': Value('us')}, None)],
        hwid.bom.components['region'])


if __name__ == '__main__':
  unittest.main()
