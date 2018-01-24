#!/usr/bin/env python
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Integration tests for the HWID v3 framework."""

import logging
import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3.bom import BOM
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.hwid.v3.rule import RuleException


_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')

_TEST_DATABASE_PATH = os.path.join(_TEST_DATA_PATH, 'TEST_PROJECT')

_TEST_PROBED_RESULTS_PATH = os.path.join(
    _TEST_DATA_PATH, 'TEST_PROJECT_probed_results')

_TEST_INVALID_PROBED_RESULTS_PATH = os.path.join(
    _TEST_DATA_PATH, 'TEST_PROJECT_invalid_probed_results')


class TestData(object):
  def __init__(self, encoded_string, image_id, update_components=None,
               device_info=None, rma_mode=None):
    components = {
        'audio_codec': ['codec_0', 'hdmi_0'],
        'battery': ['battery_unsupported'],
        'bluetooth': ['bluetooth_0'],
        'cellular': [],
        'cpu': ['cpu_0'],
        'display_panel': ['display_panel_0'],
        'dram': ['dram_0'],
        'embedded_controller': ['embedded_controller_0'],
        'firmware_keys': ['firmware_keys_premp'],
        'flash_chip': [] if image_id in [0, 1] else ['flash_chip_0'],
        'keyboard': ['keyboard_us'],
        'region': [],
        'ro_ec_firmware': ['ro_ec_firmware_0'],
        'ro_main_firmware': ['ro_main_firmware_0'],
        'storage': ['storage_0'],
        'video': ['camera_0'],
    }
    if update_components is not None:
      components.update(update_components)

    self.encoded_string = encoded_string
    self.bom = BOM(0, image_id, components)
    self.device_info = device_info or {}
    self.rma_mode = rma_mode


_TEST_DATA_CAN_GENERATE = [
    TestData('CHROMEBOOK D9L-S3Q-A9G', 3,
             dict(audio_codec=['codec_1', 'hdmi_1'],
                  battery=['battery_supported'],
                  cpu=['cpu_5'],
                  dram=['dram_1', 'dram_1'],
                  firmware_keys=['firmware_keys_mp'],
                  region=['tw'],
                  ro_main_firmware=['ro_main_firmware_1']),
             {'component.has_cellular': False},
             False),
    TestData('CHROMEBOOK D5Q-Q3Q-A3F', 3,
             dict(battery=['battery_supported'],
                  cellular=['cellular_0'],
                  cpu=['cpu_4'],
                  firmware_keys=['firmware_keys_mp']),
             {'component.has_cellular': True},
             True),
]

_TEST_DATA_RELEASED = [
    TestData('CHROMEBOOK AIEB-ED', 0,
             dict(battery=['battery_unqualified'],
                  ro_main_firmware=['ro_main_firmware_1'])),
    TestData('CHROMEBOOK ANUB-CX', 0,
             dict(battery=['battery_supported'],
                  cpu=['cpu_1'],
                  dram=['dram_2', 'dram_2', 'dram_2'],
                  ro_main_firmware=['ro_main_firmware_1'])),
    TestData('CHROMEBOOK AEAB-HD', 0, dict(battery=['battery_deprecated'])),
    TestData('CHROMEBOOK BMAB-VV', 1, dict(battery=['battery_supported'])),
    TestData('CHROMEBOOK D3B-A2Q-A8C', 3,
             dict(battery=['battery_deprecated'],
                  ro_main_firmware=['ro_main_firmware_1'])),
]

_TEST_DATA_BREAK_VERIFY_RULES = TestData(
    'CHROMEBOOK D9D-S2Q-A2Q', 3,
    dict(audio_codec=['codec_1', 'hdmi_1'],
         battery=['battery_supported'],
         dram=['dram_1', 'dram_1'],
         firmware_keys=['firmware_keys_mp'],
         region=['tw'],
         ro_main_firmware=['ro_main_firmware_1']))

_TEST_DATA_BAD_COMPONENT_STATUS = TestData(
    'CHROMEBOOK D6L-S3Q-A3T', 3,
    dict(audio_codec=['codec_1', 'hdmi_1'],
         cpu=['cpu_5'],
         dram=['dram_1', 'dram_1'],
         firmware_keys=['firmware_keys_mp'],
         region=['tw'],
         ro_main_firmware=['ro_main_firmware_1']))

_TEST_DATA_INVALID_ENCODED_STRING = [
    'CHROMEBOOK ANUB-XX',
    'CHROMEBOOK ANUB-2233-44WN',
    'CHROME?OOK ANUB-CX',
    'CHROMEBOOK#ANUB-CX',
    'CHROMEBOOK AIEZ-GV',
]


def _LoadMultiProbedResults(path):
  with open(path, 'r') as f:
    return [hwid_utils.GetProbedResults(raw_data=raw_data)
            for raw_data in f.read().split('##### SPLITLINE #####')]


class _CustomAssertions(object):
  def assertBOMEquals(self, bom1, bom2):
    self.assertEquals(bom1.encoding_pattern_index, bom2.encoding_pattern_index)
    self.assertEquals(bom1.image_id, bom2.image_id)
    self.assertEquals(set(bom1.components.keys()), set(bom2.components.keys()))
    for comp_cls, bom1_comp_names in bom1.components.iteritems():
      self.assertEquals(bom1_comp_names, bom2.components[comp_cls])


class GenerateHWIDTest(unittest.TestCase, _CustomAssertions):
  def setUp(self):
    self.database = Database.LoadFile(_TEST_DATABASE_PATH)
    self.probed_results = _LoadMultiProbedResults(_TEST_PROBED_RESULTS_PATH)
    self.invalid_probed_results = _LoadMultiProbedResults(
        _TEST_INVALID_PROBED_RESULTS_PATH)

  def testSucc(self):
    for i, test_data in enumerate(_TEST_DATA_CAN_GENERATE):
      generated_encoded_string = hwid_utils.GenerateHWID(
          self.database, self.probed_results[i],
          test_data.device_info, {}, test_data.rma_mode).encoded_string
      self.assertEquals(generated_encoded_string, test_data.encoded_string)

  def testBadComponentStatus(self):
    for i, test_data in enumerate(_TEST_DATA_CAN_GENERATE):
      if not test_data.rma_mode:
        continue
      self.assertRaises(common.HWIDException, hwid_utils.GenerateHWID,
                        self.database, self.probed_results[i],
                        test_data.device_info, {}, rma_mode=False)

  def testBadProbedResults(self):
    for probed_results in self.invalid_probed_results:
      self.assertRaises(common.HWIDException, hwid_utils.GenerateHWID,
                        self.database, probed_results,
                        {'component.has_cellular': True}, {}, False)


class DecodeHWIDTest(unittest.TestCase, _CustomAssertions):
  def setUp(self):
    self.database = Database.LoadFile(_TEST_DATABASE_PATH)

  def testSucc(self):
    for test_data in (_TEST_DATA_CAN_GENERATE +
                      _TEST_DATA_RELEASED +
                      [_TEST_DATA_BREAK_VERIFY_RULES] +
                      [_TEST_DATA_BAD_COMPONENT_STATUS]):
      _, decoded_bom = hwid_utils.DecodeHWID(
          self.database, test_data.encoded_string)

      self.assertBOMEquals(decoded_bom, test_data.bom)

  def testInvalidEncodedString(self):
    for encoded_string in _TEST_DATA_INVALID_ENCODED_STRING:
      self.assertRaises(common.HWIDException, hwid_utils.DecodeHWID,
                        self.database, encoded_string)


class VerifyHWIDTest(unittest.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(_TEST_DATABASE_PATH)
    self.probed_results = _LoadMultiProbedResults(_TEST_PROBED_RESULTS_PATH)
    self.default_device_info = _TEST_DATA_CAN_GENERATE[0].device_info

  def testSucc(self):
    for i, test_data in enumerate(_TEST_DATA_CAN_GENERATE):
      hwid_utils.VerifyHWID(self.database, test_data.encoded_string,
                            self.probed_results[i], test_data.device_info, {},
                            test_data.rma_mode)

  def testBOMMisMatch(self):
    self.assertRaises(common.HWIDException, hwid_utils.VerifyHWID,
                      self.database, _TEST_DATA_CAN_GENERATE[0].encoded_string,
                      self.probed_results[1],
                      _TEST_DATA_CAN_GENERATE[1].device_info, {}, True)

  def testBadComponentStatus(self):
    test_data = _TEST_DATA_BAD_COMPONENT_STATUS
    self.probed_results[0]['battery'] = {
        'battery_unsupported': [{'tech': 'Battery Li-ion', 'size': '2500000'}]}
    self.assertRaises(common.HWIDException, hwid_utils.VerifyHWID,
                      self.database, test_data.encoded_string,
                      self.probed_results[0], self.default_device_info,
                      {}, False)

  def testBreakVerifyRules(self):
    test_data = _TEST_DATA_BREAK_VERIFY_RULES
    self.probed_results[0]['cpu'] = {
        'cpu_0': [{'name': 'CPU @ 1.80GHz', 'cores': '4'}]}
    self.assertRaises(RuleException, hwid_utils.VerifyHWID,
                      self.database, test_data.encoded_string,
                      self.probed_results[0], self.default_device_info,
                      {}, False)

  def testInvalidEncodedString(self):
    for encoded_string in _TEST_DATA_INVALID_ENCODED_STRING:
      self.assertRaises(common.HWIDException, hwid_utils.VerifyHWID,
                        self.database, encoded_string,
                        self.probed_results[0], self.default_device_info,
                        {}, False)


class ListComponentsTest(unittest.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(_TEST_DATABASE_PATH)

  def _TestListComponents(self, comp_cls, expected_results):
    def _ConvertToSets(orig_dict):
      return {key: set(value) for key, value in orig_dict.iteritems()}

    results = hwid_utils.ListComponents(self.database, comp_cls)
    self.assertEquals(_ConvertToSets(results), _ConvertToSets(expected_results))

  def testSingleComponentClass(self):
    self._TestListComponents(
        'cpu', {'cpu': ['cpu_0', 'cpu_1', 'cpu_2', 'cpu_3', 'cpu_4', 'cpu_5']})

  def testMultipleComponentClass(self):
    self._TestListComponents(
        ['bluetooth', 'display_panel'],
        {'bluetooth': ['bluetooth_0'], 'display_panel': ['display_panel_0']})

  def testAllComponentClass(self):
    # Too many entries, just do some simple test.
    results = hwid_utils.ListComponents(self.database)
    self.assertEquals(len(results), 16)
    self.assertIn('keyboard', results)
    self.assertIn('cpu', results)
    self.assertIn('battery', results)
    self.assertIn('dram', results)
    self.assertEquals(
        set(results['dram']), set(['dram_0', 'dram_1', 'dram_2']))


class EnumerateHWIDTest(unittest.TestCase, _CustomAssertions):
  def setUp(self):
    self.database = Database.LoadFile(_TEST_DATABASE_PATH)
    self.default_combinations = {
        field_name: len(self.database.GetEncodedField(field_name))
        for field_name in self.database.encoded_fields}

  def _CalculateNumCombinations(self, **kwargs):
    result = 1
    for key, value in self.default_combinations.iteritems():
      value = kwargs.get(key, value)
      if value is None:
        continue
      result *= value
    return result

  def testSupported(self):
    for kwargs in [{}, {'status': 'supported'}]:
      kwargs['comps'] = {'storage': ['storage_0']}
      results = hwid_utils.EnumerateHWID(self.database, **kwargs)
      self.assertEquals(len(results), self._CalculateNumCombinations(
          battery_field=1,  # only battery_supported is available
          firmware_field=1,  # ro_main_firmware_1 is deprecated
          storage_field=1))

      for test_data in _TEST_DATA_CAN_GENERATE:
        if test_data.rma_mode:
          continue
        encoded_string = test_data.encoded_string
        self.assertIn(encoded_string, results,
                      'Encoded string %r is not found.' % encoded_string)
        self.assertBOMEquals(results[encoded_string], test_data.bom)

  def testReleased(self):
    results = hwid_utils.EnumerateHWID(self.database, status='released',
                                       comps={'cpu': ['cpu_0'],
                                              'storage': ['storage_0']})
    # both battery_supported, battery_deprecated is available
    self.assertEquals(
        len(results), self._CalculateNumCombinations(battery_field=2,
                                                     cpu_field=1,
                                                     storage_field=1))

  def testAll(self):
    results = hwid_utils.EnumerateHWID(self.database, status='all',
                                       comps={'cpu': ['cpu_0'],
                                              'region': ['us'],
                                              'storage': ['storage_0']})
    self.assertEquals(
        len(results), self._CalculateNumCombinations(cpu_field=1,
                                                     region_field=1,
                                                     storage_field=1))

  def testPrevImageId(self):
    results = hwid_utils.EnumerateHWID(self.database, image_id=0, status='all',
                                       comps={'region': ['us'],
                                              'storage': ['storage_0']})
    self.assertEquals(len(results), self._CalculateNumCombinations(
        flash_chip_field=None, cpu_field=2, region_field=1, storage_field=1))

  def testNoResult(self):
    results = hwid_utils.EnumerateHWID(self.database, image_id=0, status='all',
                                       comps={'storage': ['storage_999']})
    self.assertEquals(len(results), 0)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
