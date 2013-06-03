#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=W0212

import copy
import os
import unittest2
import yaml
import factory_common # pylint: disable=W0611

from cros.factory.common import MakeSet, MakeList
from cros.factory.hwid.common import HWIDException, ProbedComponentResult
from cros.factory.hwid.database import Database
from cros.factory.hwid.encoder import Encode
from cros.factory.rule import Value

_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


class HWIDTest(unittest2.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(os.path.join(_TEST_DATA_PATH,
                                                   'test_db.yaml'))
    self.results = [
        yaml.dump(result) for result in yaml.load_all(open(os.path.join(
            _TEST_DATA_PATH, 'test_probe_result.yaml')).read())]

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

  def testVerifySelf(self):
    bom = self.database.ProbeResultToBOM(self.results[0])
    bom = self.database.UpdateComponentsOfBOM(bom, {
        'keyboard': 'keyboard_us', 'dram': 'dram_0',
        'display_panel': 'display_panel_0'})
    hwid = Encode(self.database, bom)
    self.assertEquals(None, hwid.VerifySelf())

    # The correct binary string: '000000000011101000001100'
    original_value = hwid.binary_string
    hwid.binary_string = '00000000001110100000101100'
    self.assertRaisesRegexp(
        HWIDException, r'Invalid bit string length', hwid.VerifySelf)
    hwid.binary_string = '0000000001111010000011000'
    self.assertRaisesRegexp(
        HWIDException,
        r"Encoded string CHROMEBOOK AA5A-Y6L does not decode to binary string "
        r"'0000000001111010000011000'",
        hwid.VerifySelf)
    hwid.binary_string = original_value

    original_value = hwid.encoded_string
    hwid.encoded_string = 'ASDF QWER-TY'
    self.assertRaisesRegexp(
        HWIDException, r'Invalid board name', hwid.VerifySelf)
    hwid.encoded_string = original_value

    original_value = hwid.bom
    hwid.bom.encoded_fields['cpu'] = 10
    self.assertRaisesRegexp(
        HWIDException, r'Encoded fields .* have unknown indices',
        hwid.VerifySelf)
    hwid.bom.encoded_fields['cpu'] = 2
    self.assertRaisesRegexp(
        HWIDException,
        r"Binary string '0000000000111010000011000' does not decode to BOM",
        hwid.VerifySelf)
    hwid.bom = original_value

  def testVerifyProbeResult(self):
    result = self.results[0]
    bom = self.database.ProbeResultToBOM(result)
    bom = self.database.UpdateComponentsOfBOM(bom, {
        'keyboard': 'keyboard_us', 'dram': 'dram_0',
        'display_panel': 'display_panel_0'})
    hwid = Encode(self.database, bom)
    fake_result = result.replace('HDMI 1', 'HDMI 0')
    self.assertRaisesRegexp(
        HWIDException, r"Component class 'audio_codec' has extra components: "
        r"\['hdmi_0'\] and missing components: \['hdmi_1'\]. "
        r"Expected components are: \['codec_1', 'hdmi_1'\]",
        hwid.VerifyProbeResult, fake_result)
    fake_result = result.replace('name: CPU @ 2.80GHz',
                                 'name: CPU @ 2.40GHz')
    self.assertRaisesRegexp(
        HWIDException, r"Component class 'cpu' has extra components: "
        r"\['cpu_3'\] and missing components: \['cpu_5'\]. "
        r"Expected components are: \['cpu_5'\]",
        hwid.VerifyProbeResult, fake_result)
    self.assertEquals(None, hwid.VerifyProbeResult(result))
    fake_result = result.replace('xkb:us::eng', 'xkb:gb:extd:eng')
    self.assertEquals(None, hwid.VerifyProbeResult(fake_result))

  def testGetLabels(self):
    result = self.results[0]
    bom = self.database.ProbeResultToBOM(result)
    bom = self.database.UpdateComponentsOfBOM(bom, {
        'keyboard': 'keyboard_us', 'dram': 'dram_0',
        'display_panel': 'display_panel_0'})
    hwid = Encode(self.database, bom)
    labels_dict = hwid.GetLabels()
    self.assertEquals({'dram_0': {'size': '4G'}}, labels_dict['dram'])
    self.assertEquals({'keyboard_us': {'layout': 'US'}},
                      labels_dict['keyboard'])
    self.assertEquals({'storage_0': {'size': '16G', 'technology': 'SSD'}},
                      labels_dict['storage'])


class DatabaseTest(unittest2.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(os.path.join(_TEST_DATA_PATH,
                                                   'test_db.yaml'))
    self.results = [
        yaml.dump(result) for result in yaml.load_all(open(os.path.join(
            _TEST_DATA_PATH, 'test_probe_result.yaml')).read())]

  def testLoadData(self):
    self.assertRaisesRegexp(
        HWIDException, r'Invalid HWID database', Database.LoadData, '')
    self.assertRaisesRegexp(
        HWIDException, r"'board' is not specified in component database",
        Database.LoadData, {'foo': 'bar'})

  def testSanityChecks(self):
    mock_db = copy.deepcopy(self.database)
    mock_db.encoded_fields['foo'] = dict()
    mock_db.encoded_fields['foo'][0] = {'bar': ['buz']}
    self.assertRaisesRegexp(
        HWIDException,
        r"Invalid component class 'bar' in encoded_fields\['foo'\]\[0\]",
        mock_db._SanityChecks)
    mock_db.encoded_fields['foo'][0] = {'cpu': ['buz']}
    self.assertRaisesRegexp(
        HWIDException,
        r"Invalid component name 'buz' of class 'cpu' in encoded_fields"
        r"\['foo'\]\[0\]\['cpu'\]",
        mock_db._SanityChecks)

  def testProbeResultToBOM(self):
    result = self.results[0]
    bom = self.database.ProbeResultToBOM(result)
    self.assertEquals('CHROMEBOOK', bom.board)
    self.assertEquals(0, bom.encoding_pattern_index)
    self.assertEquals(0, bom.image_id)
    self.assertEquals({
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
        'camera': [('camera_0',
                    {'idVendor': Value('4567'), 'idProduct': Value('abcd'),
                     'name': Value('Camera')},
                    None)],
        'cellular': [(None, None, "Missing 'cellular' component")],
        'chipset': [('chipset_0', {'compact_str': Value('cdef:abcd')}, None)],
        'cpu': [('cpu_5',
                 {'name': Value('CPU @ 2.80GHz'), 'cores': Value('4')},
                 None)],
        'display_panel': [(None, None, "Missing 'display_panel' component")],
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
        'keyboard': [(None,
                      {'compact_str': 'xkb:us::eng'},
                      "Component class 'keyboard' is unprobeable")],
        'ro_ec_firmware': [('ro_ec_firmware_0',
                            {'compact_str': Value('ev2#ro_ec_firmware_0')},
                            None)],
        'ro_main_firmware': [('ro_main_firmware_0',
                              {'compact_str': Value('mv2#ro_main_firmware_0')},
                              None)],
        'storage': [('storage_0',
                     {'type': Value('SSD'), 'size': Value('16G'),
                      'serial': Value(r'^#123\d+$', is_re=True)},
                     None)]},
        bom.components)
    self.assertEquals({
        'audio_codec': 1,
        'battery': 3,
        'bluetooth': 0,
        'camera': 0,
        'cellular': 0,
        'chipset': 0,
        'cpu': 5,
        'display_panel': None,
        'dram': 0,
        'ec_flash_chip': 0,
        'embedded_controller': 0,
        'firmware': 0,
        'flash_chip': 0,
        'keyboard': None,
        'storage': 0}, bom.encoded_fields)

    result = yaml.load(result)
    result['found_probe_value_map']['chipset']['compact_str'] = 'something else'
    result = yaml.dump(result)
    self.assertEquals({
        'audio_codec': 1,
        'battery': 3,
        'bluetooth': 0,
        'camera': 0,
        'cellular': 0,
        'chipset': None,
        'cpu': 5,
        'display_panel': None,
        'dram': 0,
        'ec_flash_chip': 0,
        'embedded_controller': 0,
        'firmware': 0,
        'flash_chip': 0,
        'keyboard': None,
        'storage': 0}, self.database.ProbeResultToBOM(result).encoded_fields)

  def testUpdateComponentsOfBOM(self):
    bom = self.database.ProbeResultToBOM(self.results[0])
    new_bom = self.database.UpdateComponentsOfBOM(
        bom, {'keyboard': 'keyboard_gb'})
    self.assertEquals([('keyboard_gb', None, None)],
                      new_bom.components['keyboard'])
    self.assertEquals(1, new_bom.encoded_fields['keyboard'])
    new_bom = self.database.UpdateComponentsOfBOM(
        bom, {'audio_codec': ['codec_0', 'hdmi_0']})
    self.assertEquals(
        [('codec_0', {'compact_str': Value('Codec 0')}, None),
         ('hdmi_0', {'compact_str': Value('HDMI 0')}, None)],
        new_bom.components['audio_codec'])
    self.assertEquals(0, new_bom.encoded_fields['audio_codec'])
    new_bom = self.database.UpdateComponentsOfBOM(
        bom, {'cellular': 'cellular_0'})
    self.assertEquals([('cellular_0',
                        {'idVendor': Value('89ab'), 'idProduct': Value('abcd'),
                         'name': Value('Cellular Card')},
                        None)],
                       new_bom.components['cellular'])
    self.assertEquals(1, new_bom.encoded_fields['cellular'])
    new_bom = self.database.UpdateComponentsOfBOM(
        bom, {'cellular': None})
    self.assertEquals([(None, None, "Missing 'cellular' component")],
                       new_bom.components['cellular'])
    self.assertEquals(0, new_bom.encoded_fields['cellular'])
    self.assertRaisesRegexp(
        HWIDException,
        r"Invalid component class 'foo'",
        self.database.UpdateComponentsOfBOM, bom, {'foo': 'bar'})
    self.assertRaisesRegexp(
        HWIDException,
        r"Invalid component name 'bar' of class 'cpu'",
        self.database.UpdateComponentsOfBOM, bom, {'cpu': 'bar'})

  def testGetFieldIndexFromComponents(self):
    bom = self.database.ProbeResultToBOM(self.results[0])
    self.assertEquals(5, self.database._GetFieldIndexFromProbedComponents(
        'cpu', bom.components))
    self.assertEquals(1, self.database._GetFieldIndexFromProbedComponents(
        'audio_codec', bom.components))
    self.assertEquals(3, self.database._GetFieldIndexFromProbedComponents(
        'battery', bom.components))
    self.assertEquals(0, self.database._GetFieldIndexFromProbedComponents(
        'storage', bom.components))
    self.assertEquals(0, self.database._GetFieldIndexFromProbedComponents(
        'cellular', bom.components))
    self.assertEquals(None, self.database._GetFieldIndexFromProbedComponents(
        'wimax', bom.components))

  def testGetAllIndices(self):
    self.assertEquals([0, 1, 2, 3, 4, 5], self.database._GetAllIndices('cpu'))
    self.assertEquals([0, 1], self.database._GetAllIndices('dram'))
    self.assertEquals([0], self.database._GetAllIndices('display_panel'))

  def testGetAttributesByIndex(self):
    self.assertEquals({'battery': [{
                          'name': 'battery_large',
                          'values': {
                              'tech': Value('Battery Li-ion'),
                              'size': Value('7500000')}}]},
                      self.database._GetAttributesByIndex('battery', 2))
    self.assertEquals(
        {'hash_gbb': [{
              'name': 'hash_gbb_0',
              'values': {
                  'compact_str': Value('gv2#hash_gbb_0')}}],
         'key_recovery': [{
              'name': 'key_recovery_0',
              'values': {
                  'compact_str': Value('kv3#key_recovery_0')}}],
         'key_root': [{
              'name': 'key_root_0',
              'values': {
                  'compact_str': Value('kv3#key_root_0')}}],
         'ro_ec_firmware': [{
              'name': 'ro_ec_firmware_0',
              'values': {
                  'compact_str': Value('ev2#ro_ec_firmware_0')}}],
         'ro_main_firmware': [{
              'name': 'ro_main_firmware_0',
              'values': {
                  'compact_str': Value('mv2#ro_main_firmware_0')}}]},
        self.database._GetAttributesByIndex('firmware', 0))
    self.assertEquals({
        'audio_codec': [
            {'name': 'codec_0', 'values': {'compact_str': Value('Codec 0')}},
            {'name': 'hdmi_0', 'values': {'compact_str': Value('HDMI 0')}}]},
        self.database._GetAttributesByIndex('audio_codec', 0))
    self.assertEquals({'cellular': None},
                      self.database._GetAttributesByIndex('cellular', 0))

  def testVerifyBinaryString(self):
    self.assertEquals(
        None, self.database.VerifyBinaryString('0000000000111010000011000'))
    self.assertRaisesRegexp(
        HWIDException, r'Invalid binary string: .*',
        self.database.VerifyBinaryString, '020001010011011011000')
    self.assertRaisesRegexp(
        HWIDException, r'Binary string .* does not have stop bit set',
        self.database.VerifyBinaryString, '00000')
    self.assertRaisesRegexp(
        HWIDException, r'Invalid bit string length',
        self.database.VerifyBinaryString, '000000000010100110110111000')

  def testVerifyEncodedString(self):
    self.assertEquals(
        None, self.database.VerifyEncodedString('CHROMEBOOK AW3L-M7I7-V'))
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
    bom = self.database.ProbeResultToBOM(self.results[0])
    self.assertEquals(
        None, self.database.VerifyBOM(bom))

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
    bom.encoding_pattern_index = 2
    self.assertRaisesRegexp(
        HWIDException, r'Invalid encoding pattern', self.database.VerifyBOM,
        bom)
    bom.encoding_pattern_index = original_value

    original_value = bom.image_id
    bom.image_id = 6
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
    bom.components['cpu'] = [ProbedComponentResult(
        'cpu', {'name': Value('foo'), 'cores': Value('4')}, None)]
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

  def testVerifyComponents(self):
    self.maxDiff = None
    self.assertRaisesRegexp(
        HWIDException, r'Argument comp_list should be a list',
        self.database.VerifyComponents, self.results[0], 'cpu')
    self.assertRaisesRegexp(
        HWIDException,
        r"\['keyboard'\] do not have probe values and cannot be verified",
        self.database.VerifyComponents, self.results[0], ['keyboard'])
    self.assertEquals({
        'audio_codec': [
            ('codec_1', {'compact_str': Value('Codec 1')}, None),
            ('hdmi_1', {'compact_str': Value('HDMI 1')}, None)],
        'cellular': [
            (None, None, "Missing 'cellular' component")],
        'cpu': [
            ('cpu_5', {'name': Value('CPU @ 2.80GHz'), 'cores': Value('4')},
             None)]},
        self.database.VerifyComponents(
            self.results[0], ['audio_codec', 'cellular', 'cpu']))
    self.assertEquals({
        'audio_codec': [
            ('codec_1', {'compact_str': Value('Codec 1')}, None),
            (None, {'compact_str': 'HDMI 3'},
             "Unsupported 'audio_codec' component found with probe result "
             "{ 'compact_str': 'HDMI 3'} (no matching name in the "
             "component DB)")
        ]}, self.database.VerifyComponents(self.results[1], ['audio_codec']))
    self.assertEquals({
        'storage': [
            (None, {'type': 'SSD', 'size': '16G', 'serial': '#1234aa'},
             "Unsupported 'storage' component found with probe result "
             "{ 'serial': '#1234aa', 'size': '16G', 'type': 'SSD'} "
             "(no matching name in the component DB)")]},
        self.database.VerifyComponents(self.results[2], ['storage']))


if __name__ == '__main__':
  unittest2.main()
