#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.common import HWIDException
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.hwid.v3.rule import Value
from cros.factory.hwid.v3 import transformer
from cros.factory.hwid.v3 import verifier
from cros.factory.utils import json_utils


_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


class IsMPKeyNameTest(unittest.TestCase):

  def testPreMP(self):
    self.assertFalse(verifier.IsMPKeyName('foo_premp'))
    self.assertFalse(verifier.IsMPKeyName('foo_pre_mp'))
    self.assertFalse(verifier.IsMPKeyName('foo_pre_mp_v2'))
    self.assertFalse(verifier.IsMPKeyName('foo_pre_mpv2'))
    self.assertFalse(verifier.IsMPKeyName('foo_premp_v2'))

  def testMP(self):
    self.assertTrue(verifier.IsMPKeyName('foo_mp'))
    self.assertTrue(verifier.IsMPKeyName('foo_mp_v2'))
    self.assertTrue(verifier.IsMPKeyName('foo_mpv2'))

  def testDev(self):
    self.assertFalse(verifier.IsMPKeyName('foo_dev'))


class VerifyBOMTest(unittest.TestCase):

  def setUp(self):
    self.database = Database.LoadFile(os.path.join(_TEST_DATA_PATH,
                                                   'test_db.yaml'))
    self.results = json_utils.LoadFile(
        os.path.join(_TEST_DATA_PATH, 'test_probe_result.json'))

  def testVerifyProbeResult(self):
    result = self.results[0]
    orig_bom = hwid_utils.GenerateBOMFromProbedResults(self.database, result)
    self.database.UpdateComponentsOfBOM(orig_bom, {
        'keyboard': 'keyboard_us', 'dram': 'dram_0',
        'display_panel': 'display_panel_0'})
    orig_bom.image_id = 2
    transformer.BOMToIdentity(self.database, orig_bom)

    raw_result = json_utils.DumpStr(result)

    fake_result = json_utils.LoadStr(raw_result.replace('HDMI 1', 'HDMI 0'))
    bom = hwid_utils.GenerateBOMFromProbedResults(self.database, fake_result)
    self.assertRaisesRegexp(
        HWIDException, r"Component class 'audio_codec' has extra components: "
        r"\['hdmi_0'\] and is missing components: \['hdmi_1'\]. "
        r"Expected components are: \['codec_1', 'hdmi_1'\]",
        verifier.VerifyBOM, self.database, orig_bom, bom)
    # We only verify the components listed in the pattern. Do not raise
    # exception while the component which is not in the pattern is missing.
    fake_result = json_utils.LoadStr(raw_result.replace('EC Flash Chip',
                                                        'Foo chip'))
    bom = hwid_utils.GenerateBOMFromProbedResults(self.database, fake_result)
    self.assertEquals(None, verifier.VerifyBOM(self.database, orig_bom, bom))

    fake_result = json_utils.LoadStr(raw_result.replace(
        '"name": "CPU @ 2.80GHz"', '"name": "CPU @ 2.40GHz"'))
    bom = hwid_utils.GenerateBOMFromProbedResults(self.database, fake_result)
    self.assertRaisesRegexp(
        HWIDException, r"Component class 'cpu' has extra components: "
        r"\['cpu_3'\] and is missing components: \['cpu_5'\]. "
        r"Expected components are: \['cpu_5'\]",
        verifier.VerifyBOM, self.database, orig_bom, bom)
    bom = hwid_utils.GenerateBOMFromProbedResults(self.database, result)
    self.assertEquals(None, verifier.VerifyBOM(self.database, orig_bom, bom))
    fake_result = json_utils.LoadStr(
        raw_result.replace('xkb:us::eng', 'xkb:gb:extd:eng'))
    bom = hwid_utils.GenerateBOMFromProbedResults(self.database, fake_result)
    self.assertEquals(None, verifier.VerifyBOM(self.database, orig_bom, bom))


class VerifyComponentsTest(unittest.TestCase):

  def setUp(self):
    self.database = Database.LoadFile(os.path.join(_TEST_DATA_PATH,
                                                   'test_db.yaml'))
    self.results = json_utils.LoadFile(
        os.path.join(_TEST_DATA_PATH, 'test_probe_result.json'))
    self.boms = [hwid_utils.GenerateBOMFromProbedResults(self.database,
                                                         probed_results)
                 for probed_results in self.results]

  def testVerifyComponents(self):
    self.maxDiff = None
    bom = self.boms[0]
    self.assertRaisesRegexp(
        HWIDException, r'Argument comp_list should be a list',
        verifier.VerifyComponents, self.database, bom, 'cpu')
    self.assertRaisesRegexp(
        HWIDException,
        r"\['keyboard'\] do not have probe values and cannot be verified",
        verifier.VerifyComponents, self.database, bom, ['keyboard'])
    self.assertEquals({
        'audio_codec': [
            ('codec_1', {'compact_str': Value('Codec 1')}, None),
            ('hdmi_1', {'compact_str': Value('HDMI 1')}, None)],
        'cellular': [
            (None, None, "Missing 'cellular' component")],
        'cpu': [
            ('cpu_5', {'name': Value('CPU @ 2.80GHz'), 'cores': Value('4')},
             None)]},
                      verifier.VerifyComponents(
                          self.database, bom,
                          ['audio_codec', 'cellular', 'cpu']))
    self.assertEquals({
        'audio_codec': [
            ('codec_1', {'compact_str': Value('Codec 1')}, None),
            (None, {'compact_str': 'HDMI 3'},
             common.INVALID_COMPONENT_ERROR(
                 'audio_codec', {'compact_str': 'HDMI 3'}))
        ]}, verifier.VerifyComponents(self.database,
                                      self.boms[1], ['audio_codec']))
    self.assertEquals({
        'storage': [
            (None, {'type': 'SSD', 'size': '16G', 'serial': '#1234aa'},
             common.INVALID_COMPONENT_ERROR(
                 'storage', {'type': 'SSD',
                             'size': '16G',
                             'serial': '#1234aa'}))]},
                      verifier.VerifyComponents(self.database, self.boms[2],
                                                ['storage']))
    bom = hwid_utils.GenerateBOMFromProbedResults(
        self.database, self.results[3], loose_matching=True)
    self.assertEquals({
        'storage': [
            ('storage_2', {'type': Value('HDD'), 'size': Value('500G'),
                           'serial': Value(r'^#123\d+$', is_re=True)},
             None)]},
                      verifier.VerifyComponents(self.database,
                                                bom, ['storage']))
    self.assertEquals({
        'storage': [
            (None, {'foo': 'bar'},
             common.INVALID_COMPONENT_ERROR('storage', {'foo': 'bar'}))]},
                      verifier.VerifyComponents(self.database,
                                                self.boms[4], ['storage']))


if __name__ == '__main__':
  unittest.main()
