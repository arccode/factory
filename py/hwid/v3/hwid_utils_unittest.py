#!/usr/bin/env python
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Integration tests for the HWID v3 framework."""

import copy
import logging
import mock
import os
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3.bom import BOM
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.hwid.v3 import yaml_wrapper as yaml
from cros.factory.hwid.v3.rule import RuleException
from cros.factory.utils import json_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import yaml_utils


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
        'flash_chip': ['flash_chip_0'],
        'keyboard': ['keyboard_us'],
        'region': [],
        'ro_ec_firmware': ['ro_ec_firmware_0'],
        'ro_main_firmware': ['ro_main_firmware_0'],
        'storage': ['storage_0'],
        'video': ['camera_0'],
    }
    if image_id in [0, 1]:
      del components['flash_chip']
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
          test_data.device_info, {}, rma_mode=test_data.rma_mode).encoded_string
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
                        {'component.has_cellular': True}, {}, rma_mode=False)


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
                            rma_mode=test_data.rma_mode)

  def testBOMMisMatch(self):
    self.assertRaises(common.HWIDException, hwid_utils.VerifyHWID,
                      self.database, _TEST_DATA_CAN_GENERATE[0].encoded_string,
                      self.probed_results[1],
                      _TEST_DATA_CAN_GENERATE[1].device_info, {}, rma_mode=True)

  def testBadComponentStatus(self):
    test_data = _TEST_DATA_BAD_COMPONENT_STATUS
    self.probed_results[0]['battery'] = {
        'battery_unsupported': [{'tech': 'Battery Li-ion', 'size': '2500000'}]}
    self.assertRaises(common.HWIDException, hwid_utils.VerifyHWID,
                      self.database, test_data.encoded_string,
                      self.probed_results[0], self.default_device_info)

  def testBreakVerifyRules(self):
    test_data = _TEST_DATA_BREAK_VERIFY_RULES
    self.probed_results[0]['cpu'] = {
        'cpu_0': [{'name': 'CPU @ 1.80GHz', 'cores': '4'}]}
    self.assertRaises(RuleException, hwid_utils.VerifyHWID,
                      self.database, test_data.encoded_string,
                      self.probed_results[0], self.default_device_info)

  def testInvalidEncodedString(self):
    for encoded_string in _TEST_DATA_INVALID_ENCODED_STRING:
      self.assertRaises(common.HWIDException, hwid_utils.VerifyHWID,
                        self.database, encoded_string,
                        self.probed_results[0], self.default_device_info)


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
        field_name: len(field_data)
        for field_name, field_data in self.database.encoded_fields.iteritems()}

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


class DatabaseBuilderTest(unittest.TestCase):
  def setUp(self):
    yaml_utils.ParseMappingAsOrderedDict(loader=yaml.Loader, dumper=yaml.Dumper)
    self.probed_results = json_utils.LoadFile(
        os.path.join(_TEST_DATA_PATH, 'test_builder_probe_results.json'))
    self.output_path = tempfile.mktemp()

  def tearDown(self):
    yaml_utils.ParseMappingAsOrderedDict(False, loader=yaml.Loader,
                                         dumper=yaml.Dumper)
    if os.path.exists(self.output_path):
      os.remove(self.output_path)

  def testBuildDatabase(self):
    # Build database by the probed result.
    hwid_utils.BuildDatabase(
        self.output_path, self.probed_results[0], 'CHROMEBOOK', 'EVT',
        add_default_comp=['dram'], del_comp=None,
        region=['tw', 'jp'], chassis=['FOO', 'BAR'])
    # If not in Chroot, the checksum is not updated.
    verify_checksum = sys_utils.InChroot()
    Database.LoadFile(self.output_path, verify_checksum)
    # Check the value.
    with open(self.output_path, 'r') as f:
      db = yaml.load(f.read())
    self.assertEquals(db['project'], 'CHROMEBOOK')
    self.assertEquals(db['image_id'], {0: 'EVT'})
    self.assertEquals(db['pattern'][0]['image_ids'], [0])
    self.assertEquals(db['pattern'][0]['encoding_scheme'], 'base8192')
    priority_fields = [
        # Essential fields.
        {'mainboard_field': 3},
        {'region_field': 5},
        {'chassis_field': 5},
        {'cpu_field': 3},
        {'storage_field': 5},
        {'dram_field': 5},
        # Priority fields.
        {'firmware_keys_field': 3},
        {'ro_main_firmware_field': 3},
        {'ro_ec_firmware_field': 2}]
    other_fields = [
        {'ro_pd_firmware_field': 0},
        {'wireless_field': 0},
        {'display_panel_field': 0},
        {'tpm_field': 0},
        {'flash_chip_field': 0},
        {'audio_codec_field': 0},
        {'usb_hosts_field': 0},
        {'bluetooth_field': 0}]
    # The priority fields should be at the front of the fields in order.
    self.assertEquals(priority_fields,
                      db['pattern'][0]['fields'][:len(priority_fields)])
    # The order of other fields are not guaranteed.
    for field in other_fields:
      self.assertIn(field, db['pattern'][0]['fields'])
    self.assertEquals(set(db['components'].keys()),
                      set(['dram', 'ro_pd_firmware', 'ro_main_firmware', 'tpm',
                           'storage', 'flash_chip', 'bluetooth', 'wireless',
                           'display_panel', 'audio_codec', 'firmware_keys',
                           'ro_ec_firmware', 'usb_hosts', 'cpu', 'region',
                           'mainboard', 'chassis']))
    self.assertEquals(db['rules'],
                      [{'name': 'device_info.image_id',
                        'evaluate': "SetImageId('EVT')"}])

    # Add a null component.
    # Choose to add the touchpad without a new image_id.
    with mock.patch('__builtin__.raw_input', return_value='y'):
      hwid_utils.UpdateDatabase(self.output_path, None, db,
                                add_null_comp=['touchpad', 'chassis'])
    new_db = Database.LoadFile(self.output_path, verify_checksum)
    self.assertIn({'touchpad': []},
                  new_db.encoded_fields['touchpad_field'].values())
    self.assertIn({'chassis': []},
                  new_db.encoded_fields['chassis_field'].values())

    # Add a component without a new image_id.
    probed_result = self.probed_results[0].copy()
    probed_result['touchpad'] = {'generic': [{'name': 'G_touchpad'}]}
    with mock.patch('__builtin__.raw_input', return_value='n'):
      with self.assertRaises(ValueError):
        hwid_utils.UpdateDatabase(self.output_path, probed_result, db)

    with mock.patch('__builtin__.raw_input', return_value='y'):
      hwid_utils.UpdateDatabase(self.output_path, probed_result, db)
    new_db = Database.LoadFile(self.output_path, verify_checksum)
    self.assertIn({'touchpad_field': 0}, new_db.pattern.pattern[0]['fields'])

    # Delete bluetooth, and add region and chassis.
    hwid_utils.UpdateDatabase(
        self.output_path, None, db, 'DVT',
        add_default_comp=None, del_comp=['bluetooth'],
        region=['us'], chassis=['NEW'])
    new_db = Database.LoadFile(self.output_path, verify_checksum)
    # Check the value.
    self.assertEquals(new_db.project, 'CHROMEBOOK')
    self.assertEquals(new_db.image_id, {0: 'EVT', 1: 'DVT'})
    self.assertNotIn({'bluetooth_field': 0},
                     new_db.pattern.pattern[1]['fields'])
    self.assertIn({'region': ['us']},
                  new_db.encoded_fields['region_field'].values())
    self.assertIn('NEW', new_db.components.components_dict['chassis']['items'])
    self.assertIn({'chassis': ['NEW']},
                  new_db.encoded_fields['chassis_field'].values())

  def testBuildDatabaseMissingEssentailComponent(self):
    """Tests the essential component is missing at the probe result."""
    # Essential component 'mainboard' is missing in probed result.
    probed_result = copy.deepcopy(self.probed_results[0])
    del probed_result['mainboard']

    # Deleting the essential component is not allowed.
    with self.assertRaises(ValueError):
      hwid_utils.BuildDatabase(
          self.output_path, probed_result, 'CHROMEBOOK', 'EVT',
          del_comp=['mainboard'])

    # Enter "y" to create a default item, or use add_default_comp argument.
    expected = {
        'mainboard_default': {
            'default': True,
            'status': 'unqualified',
            'values': None}}
    with mock.patch('__builtin__.raw_input', return_value='y'):
      hwid_utils.BuildDatabase(
          self.output_path, probed_result, 'CHROMEBOOK', 'EVT')
    with open(self.output_path, 'r') as f:
      db = yaml.load(f.read())
    self.assertEquals(db['components']['mainboard']['items'], expected)
    hwid_utils.BuildDatabase(
        self.output_path, probed_result, 'CHROMEBOOK', 'EVT',
        add_default_comp=['mainboard'])
    with open(self.output_path, 'r') as f:
      db = yaml.load(f.read())
    self.assertEquals(db['components']['mainboard']['items'], expected)

    # Enter "n" to create a default item, or use add_null_comp argument.
    with mock.patch('__builtin__.raw_input', return_value='n'):
      hwid_utils.BuildDatabase(
          self.output_path, probed_result, 'CHROMEBOOK', 'EVT')
    with open(self.output_path, 'r') as f:
      db = yaml.load(f.read())
    self.assertEquals(db['components']['mainboard']['items'], {})
    self.assertEquals(db['encoded_fields']['mainboard_field'],
                      {0: {'mainboard': None}})
    hwid_utils.BuildDatabase(
        self.output_path, probed_result, 'CHROMEBOOK', 'EVT',
        add_null_comp=['mainboard'])
    with open(self.output_path, 'r') as f:
      db = yaml.load(f.read())
    self.assertEquals(db['components']['mainboard']['items'], {})
    self.assertEquals(db['encoded_fields']['mainboard_field'],
                      {0: {'mainboard': None}})

  def testDeprecateDefaultItem(self):
    """Tests the default item should be deprecated after adding a item."""
    probed_result = copy.deepcopy(self.probed_results[0])
    del probed_result['mainboard']
    hwid_utils.BuildDatabase(
        self.output_path, probed_result, 'CHROMEBOOK', 'EVT',
        add_default_comp=['mainboard'])
    with open(self.output_path, 'r') as f:
      db = yaml.load(f.read())
    self.assertEquals(
        db['components']['mainboard']['items']['mainboard_default'],
        {'default': True,
         'status': 'unqualified',
         'values': None})
    hwid_utils.UpdateDatabase(self.output_path, self.probed_results[0], db)
    new_db = Database.LoadFile(self.output_path, False)
    comp_dict = new_db.components.components_dict
    self.assertEquals(
        comp_dict['mainboard']['items']['mainboard_default'],
        {'default': True,
         'status': 'unsupported',
         'values': None})


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
