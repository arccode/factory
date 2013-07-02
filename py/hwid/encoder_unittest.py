#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest
import yaml
import factory_common # pylint: disable=W0611

from cros.factory.hwid.common import HWIDException
from cros.factory.hwid.database import Database
from cros.factory.hwid.encoder import BOMToBinaryString
from cros.factory.hwid.encoder import BinaryStringToEncodedString, Encode

_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


class EncoderTest(unittest.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(os.path.join(_TEST_DATA_PATH,
                                                   'test_db.yaml'))
    self.results = [
        yaml.dump(result) for result in yaml.load_all(open(os.path.join(
            _TEST_DATA_PATH, 'test_probe_result.yaml')).read())]

  def testBOMToBinaryString(self):
    bom = self.database.ProbeResultToBOM(self.results[0])
    # Manually set unprobeable components.
    bom = self.database.UpdateComponentsOfBOM(bom, {
        'keyboard': 'keyboard_us', 'display_panel': 'display_panel_0'})
    self.assertEquals(
        '0000000000111010000011', BOMToBinaryString(self.database, bom))
    # Change firmware's encoded index to 1.
    mocked_bom = self.database.UpdateComponentsOfBOM(
        bom, {'ro_main_firmware': 'ro_main_firmware_1'})
    self.assertEquals(
        '0000000001111010000011', BOMToBinaryString(self.database, mocked_bom))
    # Change image id to 2.
    mocked_bom.image_id = 2
    self.assertEquals(
        '0001000001111010000011', BOMToBinaryString(self.database, mocked_bom))
    # Change encoding pattern index to 1.
    mocked_bom.encoding_pattern_index = 1
    self.assertEquals(
        '1001000001111010000011', BOMToBinaryString(self.database, mocked_bom))

  def testBinaryStringToEncodedString(self):
    self.assertEquals('CHROMEBOOK A5AU-LU',
                      BinaryStringToEncodedString(
                          self.database, '000001110100000101'))
    self.assertEquals('CHROMEBOOK C9I-F4N',
                      BinaryStringToEncodedString(
                          self.database, '000101110100000101'))

  def testEncode(self):
    bom = self.database.ProbeResultToBOM(self.results[0])
    # Manually set unprobeable components.
    bom = self.database.UpdateComponentsOfBOM(bom, {
        'keyboard': 'keyboard_us', 'display_panel': 'display_panel_0'})
    bom.image_id = 0
    hwid = Encode(self.database, bom)
    self.assertEquals('0000000000111010000011', hwid.binary_string)
    self.assertEquals('CHROMEBOOK AA5A-Y6L', hwid.encoded_string)

    bom.image_id = 2
    hwid = Encode(self.database, bom)
    self.assertEquals('0001000000111010000011', hwid.binary_string)
    self.assertEquals('CHROMEBOOK C2H-I3Q-A6Q', hwid.encoded_string)

  def testEncodeError(self):
    # Missing required component 'dram'.
    mock_results = yaml.load(self.results[0])
    mock_results['found_probe_value_map'].pop('dram')
    mock_results['missing_component_classes'].append('dram')
    bom = self.database.ProbeResultToBOM(yaml.dump(mock_results))
    bom = self.database.UpdateComponentsOfBOM(bom, {
        'keyboard': 'keyboard_us', 'display_panel': 'display_panel_0'})
    self.assertRaisesRegexp(
        HWIDException, r"Missing 'dram' component", Encode, self.database, bom)

    # Unsupported probe values of component 'dram'.
    mock_results = yaml.load(self.results[0])
    mock_results['found_probe_value_map']['dram'] = {
        'vendor': 'FOO', 'size': '4G'}
    bom = self.database.ProbeResultToBOM(yaml.dump(mock_results))
    bom = self.database.UpdateComponentsOfBOM(bom, {
        'keyboard': 'keyboard_us', 'display_panel': 'display_panel_0'})
    self.assertRaisesRegexp(
        HWIDException, r"Invalid 'dram' component found with probe result "
        "{ 'size': '4G', 'vendor': 'FOO'} \(no matching name in the component "
        "DB\)", Encode, self.database, bom)

if __name__ == '__main__':
  unittest.main()
