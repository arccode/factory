#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=W0212

import os
import unittest
import factory_common  # pylint: disable=W0611

from cros.factory.hwid.v3.common import HWID
from cros.factory.hwid.v3.common import HWIDException
from cros.factory.hwid.v3.common import IsMPKeyName
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.hwid.v3.transformer import Encode
from cros.factory.utils import json_utils

_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


class IsMPKeyNameTest(unittest.TestCase):

  def testPreMP(self):
    self.assertFalse(IsMPKeyName('foo_premp'))
    self.assertFalse(IsMPKeyName('foo_pre_mp'))
    self.assertFalse(IsMPKeyName('foo_pre_mp_v2'))
    self.assertFalse(IsMPKeyName('foo_pre_mpv2'))
    self.assertFalse(IsMPKeyName('foo_premp_v2'))

  def testMP(self):
    self.assertTrue(IsMPKeyName('foo_mp'))
    self.assertTrue(IsMPKeyName('foo_mp_v2'))
    self.assertTrue(IsMPKeyName('foo_mpv2'))

  def testDev(self):
    self.assertFalse(IsMPKeyName('foo_dev'))


class HWIDTest(unittest.TestCase):

  def setUp(self):
    self.database = Database.LoadFile(os.path.join(_TEST_DATA_PATH,
                                                   'test_db.yaml'))
    self.results = json_utils.LoadFile(
        os.path.join(_TEST_DATA_PATH, 'test_probe_result.json'))

  def testInvalidInitialize(self):
    bom = hwid_utils.GenerateBOMFromProbedResults(self.database,
                                                  self.results[0])
    self.database.UpdateComponentsOfBOM(bom, {
        'keyboard': 'keyboard_us', 'dram': 'dram_0',
        'display_panel': 'display_panel_0'})
    bom.image_id = 2
    with self.assertRaisesRegexp(HWIDException,
                                 'Invalid operation mode'):
      HWID(self.database, bom, mode='UNKNOWN')

  def testIsEquivalentBinaryString(self):
    self.assertTrue(HWID.IsEquivalentBinaryString('01001', '01001'))
    self.assertTrue(HWID.IsEquivalentBinaryString('01011', '010100001'))
    self.assertFalse(HWID.IsEquivalentBinaryString('01011', '010110001'))
    self.assertFalse(HWID.IsEquivalentBinaryString('01011', '011110001'))
    with self.assertRaises(AssertionError):
      HWID.IsEquivalentBinaryString('010110', '01011000')

  def testVerifySelf(self):
    bom = hwid_utils.GenerateBOMFromProbedResults(self.database,
                                                  self.results[0])
    self.database.UpdateComponentsOfBOM(bom, {
        'keyboard': 'keyboard_us', 'dram': 'dram_0',
        'display_panel': 'display_panel_0'})
    bom.image_id = 2
    hwid = Encode(self.database, bom)
    self.assertEquals(None, hwid.VerifySelf())

    with self.assertRaises(AttributeError):
      hwid.binary_string = 'CANNOT SET binary_string'

    with self.assertRaises(AttributeError):
      hwid.encoded_string = 'CANNOT SET encoded_string'

    original_value = hwid.bom
    hwid.bom.encoded_fields['cpu'] = 10
    self.assertRaisesRegexp(
        HWIDException, r'Encoded fields .* have unknown indices',
        hwid.VerifySelf)
    hwid.bom = original_value

  def testVerifyProbeResult(self):
    result = self.results[0]
    bom = hwid_utils.GenerateBOMFromProbedResults(self.database, result)
    self.database.UpdateComponentsOfBOM(bom, {
        'keyboard': 'keyboard_us', 'dram': 'dram_0',
        'display_panel': 'display_panel_0'})
    bom.image_id = 2
    hwid = Encode(self.database, bom)

    raw_result = json_utils.DumpStr(result)

    fake_result = json_utils.LoadStr(raw_result.replace('HDMI 1', 'HDMI 0'))
    bom = hwid_utils.GenerateBOMFromProbedResults(self.database, fake_result)
    self.assertRaisesRegexp(
        HWIDException, r"Component class 'audio_codec' has extra components: "
        r"\['hdmi_0'\] and is missing components: \['hdmi_1'\]. "
        r"Expected components are: \['codec_1', 'hdmi_1'\]",
        hwid.VerifyBOM, bom)
    # We only verify the components listed in the pattern. Do not raise
    # exception while the component which is not in the pattern is missing.
    fake_result = json_utils.LoadStr(raw_result.replace('EC Flash Chip',
                                                        'Foo chip'))
    bom = hwid_utils.GenerateBOMFromProbedResults(self.database, fake_result)
    self.assertEquals(None, hwid.VerifyBOM(bom))

    fake_result = json_utils.LoadStr(raw_result.replace(
        '"name": "CPU @ 2.80GHz"', '"name": "CPU @ 2.40GHz"'))
    bom = hwid_utils.GenerateBOMFromProbedResults(self.database, fake_result)
    self.assertRaisesRegexp(
        HWIDException, r"Component class 'cpu' has extra components: "
        r"\['cpu_3'\] and is missing components: \['cpu_5'\]. "
        r"Expected components are: \['cpu_5'\]",
        hwid.VerifyBOM, bom)
    bom = hwid_utils.GenerateBOMFromProbedResults(self.database, result)
    self.assertEquals(None, hwid.VerifyBOM(bom))
    fake_result = json_utils.LoadStr(
        raw_result.replace('xkb:us::eng', 'xkb:gb:extd:eng'))
    bom = hwid_utils.GenerateBOMFromProbedResults(self.database, fake_result)
    self.assertEquals(None, hwid.VerifyBOM(bom))


if __name__ == '__main__':
  unittest.main()
