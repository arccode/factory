#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=W0212

import os
import unittest
import yaml
import factory_common  # pylint: disable=W0611

from cros.factory.hwid.v3.common import HWID
from cros.factory.hwid.v3.common import HWIDException
from cros.factory.hwid.v3.common import IsMPKeyName
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3.encoder import Encode

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
    self.results = [
        yaml.dump(result) for result in yaml.load_all(open(os.path.join(
            _TEST_DATA_PATH, 'test_probe_result.yaml')).read())]

  def testInvalidInitialize(self):
    bom = self.database.ProbeResultToBOM(self.results[0])
    bom = self.database.UpdateComponentsOfBOM(bom, {
        'keyboard': 'keyboard_us', 'dram': 'dram_0',
        'display_panel': 'display_panel_0'})
    bom.image_id = 2
    with self.assertRaisesRegexp(HWIDException,
                                 'The last bit of binary_string must be 1.'):
      HWID(self.database, bom, binary_string='00000')
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
    bom = self.database.ProbeResultToBOM(self.results[0])
    bom = self.database.UpdateComponentsOfBOM(bom, {
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
    # We only verify the components listed in the pattern. Do not raise
    # exception while the component which is not in the pattern is missing.
    fake_result = result.replace('EC Flash Chip', 'Foo chip')
    self.assertEquals(None, hwid.VerifyProbeResult(fake_result))

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


if __name__ == '__main__':
  unittest.main()
