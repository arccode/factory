#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=W0212

import os
import unittest2
import yaml
import factory_common # pylint: disable=W0611

from cros.factory.common import MakeSet, MakeList
from cros.factory.hwid.common import HWIDException
from cros.factory.hwid.database import Database
from cros.factory.hwid.encoder import Encode

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
    bom.image_id = 2
    hwid = Encode(self.database, bom)
    self.assertEquals(None, hwid.VerifySelf())

    # The correct binary string: '0000000000111010000011'
    original_value = hwid.binary_string
    hwid.binary_string = '000000000011101000001011'
    self.assertRaisesRegexp(
        HWIDException, r'Invalid bit string length', hwid.VerifySelf)
    hwid.binary_string = '0000000001111010000011'
    self.assertRaisesRegexp(
        HWIDException,
        r"Encoded string CHROMEBOOK C2H-I3Q-A6Q does not decode to binary "
        r"string '0000000001111010000011'",
        hwid.VerifySelf)
    hwid.binary_string = original_value

    original_value = hwid.encoded_string
    hwid.encoded_string = 'ASDF CWER-TY'
    self.assertRaisesRegexp(
        HWIDException, r"Invalid HWID string format: 'ASDF CWER-TY",
        hwid.VerifySelf)
    hwid.encoded_string = original_value

    original_value = hwid.encoded_string
    hwid.encoded_string = 'ASDF C2W-E3R'
    self.assertRaisesRegexp(
        HWIDException, r"Invalid board name: 'ASDF'", hwid.VerifySelf)
    hwid.encoded_string = original_value

    original_value = hwid.bom
    hwid.bom.encoded_fields['cpu'] = 10
    self.assertRaisesRegexp(
        HWIDException, r'Encoded fields .* have unknown indices',
        hwid.VerifySelf)
    hwid.bom.encoded_fields['cpu'] = 2
    self.assertRaisesRegexp(
        HWIDException,
        r"Binary string '0001000000111010000011' does not decode to BOM",
        hwid.VerifySelf)
    hwid.bom = original_value

  def testVerifyProbeResult(self):
    result = self.results[0]
    bom = self.database.ProbeResultToBOM(result)
    bom = self.database.UpdateComponentsOfBOM(bom, {
        'keyboard': 'keyboard_us', 'dram': 'dram_0',
        'display_panel': 'display_panel_0'})
    bom.image_id = 2
    hwid = Encode(self.database, bom)
    fake_result = result.replace('HDMI 1', 'HDMI 0')
    self.assertRaisesRegexp(
        HWIDException, r"Component class 'audio_codec' has extra components: "
        r"\['hdmi_0'\] and is missing components: \['hdmi_1'\]. "
        r"Expected components are: \['codec_1', 'hdmi_1'\]",
        hwid.VerifyProbeResult, fake_result)
    fake_result = result.replace('EC Flash Chip', 'Foo chip')
    self.assertRaisesRegexp(
        HWIDException, r"Component class 'ec_flash_chip' is missing "
        r"components: \['ec_flash_chip_0'\]. Expected components are: "
        r"\['ec_flash_chip_0'\]",
        hwid.VerifyProbeResult, fake_result)
    fake_result = result.replace('name: CPU @ 2.80GHz',
                                 'name: CPU @ 2.40GHz')
    self.assertRaisesRegexp(
        HWIDException, r"Component class 'cpu' has extra components: "
        r"\['cpu_3'\] and is missing components: \['cpu_5'\]. "
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
    bom.image_id = 2
    hwid = Encode(self.database, bom)
    labels_dict = hwid.GetLabels()
    self.assertEquals({'dram_0': {'size': '4G'}}, labels_dict['dram'])
    self.assertEquals({'keyboard_us': {'layout': 'US'}},
                      labels_dict['keyboard'])
    self.assertEquals({'storage_0': {'size': '16G', 'technology': 'SSD'}},
                      labels_dict['storage'])


if __name__ == '__main__':
  unittest2.main()
