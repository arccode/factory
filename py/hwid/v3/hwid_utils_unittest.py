#!/bin/env python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for HWID v3 utility functions."""

import copy
import logging
import mock
import os
import tempfile
import unittest
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.hwid.v2 import hwid_tool
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.hwid.v3 import rule
from cros.factory.hwid.v3.rule import Value
from cros.factory.test.rules import phase
from cros.factory.utils import sys_utils
from cros.factory.utils import yaml_utils


TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')

class HWIDv3UtilsTestWithNewDatabase(unittest.TestCase):
  """Test cases for HWID v3 utilities with the new database.

  The new database adds a new image_id and a pattern, that removes display_panel
  and cellular field, and add firmware_keys field. It also adds SKU that has no
  audio_codec component.
  """

  def setUp(self):
    self.db = database.Database.LoadFile(
        os.path.join(TEST_DATA_PATH, 'NEW_TEST_BOARD'))
    self.probed_results = list(yaml.load_all(open(os.path.join(
        TEST_DATA_PATH, 'new_test_probe_result_hwid_utils.yaml')).read()))
    self.vpd = {
        'ro': {
            'region': 'us',
            'serial_number': 'foo'
        },
        'rw': {
            'gbind_attribute': '333333333333333333333333333333333333'
                               '33333333333333333333333333332dbecc73',
            'ubind_attribute': '323232323232323232323232323232323232'
                               '323232323232323232323232323256850612'
        }
    }

  def testGenerateHWID(self):
    device_info = {
        'component.keyboard': 'us',
    }
    # Test new database with audio codec
    self.assertEquals(
        'CHROMEBOOK E35-A2Y-A7B',
        hwid_utils.GenerateHWID(
            self.db, self.probed_results[0],
            device_info, self.vpd, False).encoded_string)
    # Test new database without audio codec
    self.assertEquals(
        'CHROMEBOOK E45-A2Y-A2Z',
        hwid_utils.GenerateHWID(
            self.db, self.probed_results[1],
            device_info, self.vpd, False).encoded_string)

  def testDecodeHWID(self):
    """Tests HWID decoding."""
    # Decode old HWID string
    hwid = hwid_utils.DecodeHWID(self.db, 'CHROMEBOOK D9I-F9U')
    parsed_result = hwid_utils.ParseDecodedHWID(hwid)
    self.assertNotIn('firmware_keys', parsed_result)
    self.assertEquals(parsed_result['components']['cellular'], [{None: None}])
    self.assertEquals(parsed_result['components']['audio_codec'],
                      [{'codec_1': {'compact_str': Value('Codec 1')}},
                       {'hdmi_1': {'compact_str': Value('HDMI 1')}}])
    self.assertEquals(parsed_result['components']['display_panel'],
                      [{'display_panel_0': None}])

    # Decode new HWID string with audio_codec
    hwid = hwid_utils.DecodeHWID(self.db, 'CHROMEBOOK E35-A2Y-A7B')
    parsed_result = hwid_utils.ParseDecodedHWID(hwid)
    self.assertNotIn('display_panel', parsed_result)
    self.assertNotIn('cellular', parsed_result)
    self.assertEquals(parsed_result['components']['firmware_keys'],
                      [{'firmware_keys_mp': {
                          'key_recovery': Value('kv3#key_recovery_mp'),
                          'key_root': Value('kv3#key_root_mp')}}])
    self.assertEquals(parsed_result['components']['audio_codec'],
                      [{'codec_1': {'compact_str': Value('Codec 1')}},
                       {'hdmi_1': {'compact_str': Value('HDMI 1')}}])

    # Decode new HWID string without audio_codec
    hwid = hwid_utils.DecodeHWID(self.db, 'CHROMEBOOK E45-A2Y-A2Z')
    parsed_result = hwid_utils.ParseDecodedHWID(hwid)
    self.assertNotIn('display_panel', parsed_result)
    self.assertNotIn('cellular', parsed_result)
    self.assertEquals(parsed_result['components']['firmware_keys'],
                      [{'firmware_keys_mp': {
                          'key_recovery': Value('kv3#key_recovery_mp'),
                          'key_root': Value('kv3#key_root_mp')}}])
    self.assertEquals(parsed_result['components']['audio_codec'],
                      [{None: None}])


class HWIDv3UtilsTest(unittest.TestCase):
  """Test cases for HWID v3 utilities."""

  def setUp(self):
    self.db = database.Database.LoadFile(
        os.path.join(TEST_DATA_PATH, 'TEST_BOARD'))
    self.probed_results = yaml.load(open(os.path.join(
        TEST_DATA_PATH, 'test_probe_result_hwid_utils.yaml')).read())
    self.vpd = {
        'ro': {
            'region': 'us',
            'serial_number': 'foo'
        },
        'rw': {
            'gbind_attribute': '333333333333333333333333333333333333'
                               '33333333333333333333333333332dbecc73',
            'ubind_attribute': '323232323232323232323232323232323232'
                               '323232323232323232323232323256850612'
        }
    }

  def testVerifyComponentsV3(self):
    """Test if the Gooftool.VerifyComponent() works properly.

    This test tries to probe four components [bluetooth, battery, cpu,
    audio_codec], where
      'bluetooth' returns a valid result.
      'battery' returns a false result.
      'cpu' does not return any result.
      'audio_codec' returns multiple results.
    """
    probed_results = yaml.load(hwid_tool.ProbeResults(
        found_probe_value_map={
            'bluetooth': {
                'idVendor': '0123',
                'idProduct': 'abcd',
                'bcd': '0001'},
            'battery': {
                'compact_str': 'fake value'},
            'audio_codec': [
                {'compact_str': 'Codec 1'},
                {'compact_str': 'HDMI 1'},
                {'compact_str': 'fake value'}]},
        missing_component_classes=[],
        found_volatile_values={},
        initial_configs={}).Encode())

    results = hwid_utils.VerifyComponents(
        self.db, probed_results,
        ['bluetooth', 'battery', 'cpu', 'audio_codec'])

    self.assertEquals(
        [('bluetooth_0',
          {'idVendor': rule.Value('0123'), 'idProduct': rule.Value('abcd'),
           'bcd': rule.Value('0001')},
          None)],
        results['bluetooth'])
    self.assertEquals(
        [(None, None, "Missing 'cpu' component")],
        results['cpu'])
    self.assertEquals(
        [(None, {'compact_str': 'fake value'},
          ("Invalid 'battery' component found with probe result "
           "{ 'compact_str': 'fake value'} "
           '(no matching name in the component DB)'))],
        results['battery'])
    self.assertEquals(
        [('codec_1', {'compact_str': rule.Value('Codec 1')}, None),
         ('hdmi_1', {'compact_str': rule.Value('HDMI 1')}, None),
         (None, {'compact_str': 'fake value'},
          ("Invalid 'audio_codec' component found with probe result "
           "{ 'compact_str': 'fake value'} "
           '(no matching name in the component DB)'))],
        results['audio_codec'])

  def testVerifyBadComponents3(self):
    """Tests VerifyComponents with invalid component class name."""
    probed_results = yaml.load(hwid_tool.ProbeResults(
        found_probe_value_map={},
        missing_component_classes=[],
        found_volatile_values={},
        initial_configs={}).Encode())

    self.assertRaises(common.HWIDException, hwid_utils.VerifyComponents,
                      self.db, probed_results, ['cpu', 'bad_class_name'])

  def testGenerateHWID(self):
    """Tests HWID generation."""
    device_info = {
        'component.has_cellular': False,
        'component.keyboard': 'us',
        'component.dram': 'foo',
        'component.audio_codec': 'set_1'
    }
    self.assertEquals(
        'CHROMEBOOK D9I-E4A-A2B',
        hwid_utils.GenerateHWID(
            self.db, self.probed_results,
            device_info, self.vpd, False).encoded_string)

    device_info = {
        'component.has_cellular': True,
        'component.keyboard': 'gb',
        'component.dram': 'foo',
        'component.audio_codec': 'set_1'
    }
    self.assertEquals(
        'CHROMEBOOK D92-E4A-A87',
        hwid_utils.GenerateHWID(
            self.db, self.probed_results,
            device_info, self.vpd, False).encoded_string)

    device_info = {
        'component.has_cellular': True,
        'component.keyboard': 'gb',
        'component.dram': 'foo',
        'component.audio_codec': 'set_0'
    }
    self.assertEquals(
        'CHROMEBOOK D52-E4A-A7E',
        hwid_utils.GenerateHWID(
            self.db, self.probed_results,
            device_info, self.vpd, False).encoded_string)

  def testVerifyHWID(self):
    """Tests HWID verification."""
    self.assertEquals(None, hwid_utils.VerifyHWID(
        self.db, 'CHROMEBOOK A5AU-LU', self.probed_results, self.vpd, False,
        phase.EVT))
    for current_phase in (phase.PVT, phase.PVT_DOGFOOD):
      self.assertEquals(None, hwid_utils.VerifyHWID(
          self.db, 'CHROMEBOOK D9I-F9U', self.probed_results, self.vpd, False,
          current_phase))

    # Check for mismatched phase.
    self.assertRaisesRegexp(
        common.HWIDException,
        r"In DVT phase, expected an image name beginning with 'DVT' "
        r"\(but .* has image ID 'PVT2'\)",
        hwid_utils.VerifyHWID,
        self.db, 'CHROMEBOOK D9I-F9U', self.probed_results, self.vpd, False,
        phase.DVT)

    # Check for missing RO VPD.
    vpd = copy.deepcopy(self.vpd)
    del vpd['ro']['serial_number']
    self.assertRaisesRegexp(
        rule.RuleException, r"KeyError\('serial_number',\)",
        hwid_utils.VerifyHWID, self.db, 'CHROMEBOOK D9I-F9U',
        self.probed_results, vpd, False, phase.PVT)

    # Check for invalid RO VPD.
    vpd = copy.deepcopy(self.vpd)
    vpd['ro']['region'] = 'invalid_region'
    self.assertRaisesRegexp(
        rule.RuleException,
        r"Invalid VPD value 'invalid_region' of 'region'",
        hwid_utils.VerifyHWID, self.db, 'CHROMEBOOK D9I-F9U',
        self.probed_results, vpd, False, phase.PVT)

    # Check for missing RW VPD.
    vpd = copy.deepcopy(self.vpd)
    del vpd['rw']['gbind_attribute']
    self.assertRaisesRegexp(
        rule.RuleException, r"KeyError\('gbind_attribute',\)",
        hwid_utils.VerifyHWID, self.db, 'CHROMEBOOK D9I-F9U',
        self.probed_results, vpd, False, phase.PVT)

    # Check for invalid RW VPD.
    vpd = copy.deepcopy(self.vpd)
    vpd['rw']['gbind_attribute'] = 'invalid_gbind_attribute'
    self.assertRaisesRegexp(
        rule.RuleException,
        r"Invalid registration code 'invalid_gbind_attribute'",
        hwid_utils.VerifyHWID, self.db, 'CHROMEBOOK D9I-F9U',
        self.probed_results, vpd, False, phase.PVT)

    probed_results = copy.deepcopy(self.probed_results)
    probed_results['found_probe_value_map']['audio_codec'][1] = {
        'compact_str': 'HDMI 2'}
    self.assertRaisesRegexp(
        common.HWIDException,
        (r"Component class 'audio_codec' is missing components: "
         r"\['hdmi_1'\]. Expected components are: \['codec_1', 'hdmi_1'\]"),
        hwid_utils.VerifyHWID, self.db, 'CHROMEBOOK D9I-F9U', probed_results,
        self.vpd, False, phase.PVT)

    # Test pre-MP recovery/root keys.
    probed_results = copy.deepcopy(self.probed_results)
    probed_results['found_volatile_values']['key_root'].update(
        {'compact_str': 'kv3#key_root_premp'})
    probed_results['found_volatile_values']['key_recovery'].update(
        {'compact_str': 'kv3#key_recovery_premp'})
    # Pre-MP recovery/root keys are fine in DVT...
    self.assertEquals(None, hwid_utils.VerifyHWID(
        self.db, 'CHROMEBOOK B5AW-5W', probed_results, self.vpd, False,
        phase.DVT))
    # ...but not in PVT
    self.assertRaisesRegexp(
        common.HWIDException,
        'MP keys are required in PVT, but key_recovery component name is '
        "'key_recovery_premp' and key_root component name is 'key_root_premp'",
        hwid_utils.VerifyHWID, self.db, 'CHROMEBOOK D9I-F6A-A6B',
        probed_results, self.vpd, False, phase.PVT)

    # Test deprecated component.
    probed_results = copy.deepcopy(self.probed_results)
    probed_results['found_volatile_values']['ro_main_firmware'].update(
        {'compact_str': 'mv2#ro_main_firmware_1'})
    self.assertRaisesRegexp(
        common.HWIDException, r'Not in RMA mode. Found deprecated component of '
        r"'ro_main_firmware': 'ro_main_firmware_1'",
        hwid_utils.VerifyHWID, self.db, 'CHROMEBOOK D9I-H9T', probed_results,
        self.vpd, False, phase.PVT)

    # Test deprecated component is allowed in rma mode.
    self.assertEquals(None, hwid_utils.VerifyHWID(
        self.db, 'CHROMEBOOK D9I-H9T', probed_results, self.vpd, True,
        phase.PVT))

    # Test unqualified component.
    probed_results = copy.deepcopy(self.probed_results)
    probed_results['found_probe_value_map']['dram'].update(
        {'vendor': 'DRAM 2',
         'size': '8G'})
    self.assertRaisesRegexp(
        common.HWIDException, r'Found unqualified component of '
        r"'dram': 'dram_2' in Phase\(PVT\)",
        hwid_utils.VerifyHWID, self.db,
        'CHROMEBOOK D9I-E8A-A5F', probed_results,
        self.vpd, False, phase.PVT)

    # Test unqualified component is allowed in early builds: PROTO/EVT/DVT.
    self.assertEquals(None, hwid_utils.VerifyHWID(
        self.db, 'CHROMEBOOK A5AT-PC', probed_results, self.vpd, False,
        phase.EVT))

  def testDecodeHWID(self):
    """Tests HWID decoding."""
    hwid = hwid_utils.DecodeHWID(self.db, 'CHROMEBOOK D9I-F9U')
    self.assertEquals({
        'audio_codec_field': 1,
        'battery_field': 3,
        'firmware_field': 0,
        'storage_field': 0,
        'bluetooth_field': 0,
        'video_field': 0,
        'display_panel_field': 0,
        'cellular_field': 0,
        'keyboard_field': 0,
        'dram_field': 0,
        'cpu_field': 5},
        hwid.bom.encoded_fields)

    parsed_result = hwid_utils.ParseDecodedHWID(hwid)
    self.assertEquals(parsed_result['board'], 'CHROMEBOOK')
    self.assertEquals(parsed_result['binary_string'], '000111110100000101')
    self.assertEquals(parsed_result['image_id'], 'PVT2')
    self.assertEquals(parsed_result['components'], {
        'key_recovery': [{
            'key_recovery_mp': {
                'compact_str': Value('kv3#key_recovery_mp', is_re=False)}}],
        'cellular': [{None: None}],
        'ro_main_firmware': [{
            'ro_main_firmware_0': {
                'compact_str': Value('mv2#ro_main_firmware_0', is_re=False)}}],
        'battery': [{
            'battery_huge': {
                'tech': Value('Battery Li-ion', is_re=False),
                'size': Value('10000000', is_re=False)}}],
        'hash_gbb': [{
            'hash_gbb_0': {
                'compact_str': Value('gv2#hash_gbb_0', is_re=False)}}],
        'bluetooth': [{
            'bluetooth_0': {
                'bcd': Value('0001', is_re=False),
                'idVendor': Value('0123', is_re=False),
                'idProduct': Value('abcd', is_re=False)}}],
        'key_root': [{
            'key_root_mp': {
                'compact_str': Value('kv3#key_root_mp', is_re=False)}}],
        'video': [{
            'camera_0': {
                'idVendor': Value('4567', is_re=False),
                'type': Value('webcam', is_re=False),
                'idProduct': Value('abcd', is_re=False)}}],
        'audio_codec': [
            {'codec_1': {'compact_str': Value('Codec 1', is_re=False)}},
            {'hdmi_1': {'compact_str': Value('HDMI 1', is_re=False)}}],
        'keyboard': [{'keyboard_us': None}],
        'dram': [{
            'dram_0': {
                'vendor': Value('DRAM 0', is_re=False),
                'size': Value('4G', is_re=False)}}],
        'storage': [{
            'storage_0': {
                'serial': Value('#123456', is_re=False),
                'type': Value('SSD', is_re=False),
                'size': Value('16G', is_re=False)}}],
        'display_panel': [{'display_panel_0': None}],
        'ro_ec_firmware':[{
            'ro_ec_firmware_0': {
                'compact_str': Value('ev2#ro_ec_firmware_0', is_re=False)}}],
        'cpu': [{
            'cpu_5': {
                'cores': Value('4', is_re=False),
                'name': Value('CPU @ 2.80GHz', is_re=False)}}]})


class DatabaseBuilderTest(unittest.TestCase):

  def setUp(self):
    yaml_utils.ParseMappingAsOrderedDict()
    with open(os.path.join(TEST_DATA_PATH,
                           'test_builder_probe_results.yaml'), 'r') as f:
      self.probed_results = list(yaml.load_all(f.read()))
    self.output_path = tempfile.mktemp()

  def tearDown(self):
    yaml_utils.ParseMappingAsOrderedDict(False)
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
    database.Database.LoadFile(self.output_path, verify_checksum)
    # Check the value.
    with open(self.output_path, 'r') as f:
      db = yaml.load(f.read())
    self.assertEquals(db['board'], 'CHROMEBOOK')
    self.assertEquals(db['image_id'], {0: 'EVT'})
    self.assertEquals(db['pattern'][0]['image_ids'], [0])
    self.assertEquals(db['pattern'][0]['encoding_scheme'], 'base8192')
    priority_fields = [
        # Essential fields.
        {'board_version_field': 3},
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
                           'board_version', 'chassis']))
    self.assertEquals(db['rules'],
                      [{'name': 'device_info.image_id',
                        'evaluate': "SetImageId('EVT')"}])

    # Add a null component.
    new_db = copy.deepcopy(db)
    # Choose to add the touchpad without a new image_id.
    with mock.patch('__builtin__.raw_input', return_value='y'):
      hwid_utils.UpdateDatabase(self.output_path, None, new_db,
                                add_null_comp=['touchpad', 'chassis'])
    database.Database.LoadFile(self.output_path, verify_checksum)
    self.assertIn({'touchpad': None},
                  new_db['encoded_fields']['touchpad_field'].values())
    self.assertIn({'chassis': None},
                  new_db['encoded_fields']['chassis_field'].values())

    # Add a component without a new image_id.
    probed_result = self.probed_results[0].copy()
    probed_result['found_probe_value_map']['touchpad'] = {'name': 'G_touchpad'}
    new_db = copy.deepcopy(db)
    with mock.patch('__builtin__.raw_input', return_value='n'):
      with self.assertRaises(ValueError):
        hwid_utils.UpdateDatabase(self.output_path, probed_result, new_db)

    new_db = copy.deepcopy(db)
    with mock.patch('__builtin__.raw_input', return_value='y'):
      hwid_utils.UpdateDatabase(self.output_path, probed_result, new_db)
    self.assertIn({'touchpad_field': 0}, new_db['pattern'][0]['fields'])

    # Delete bluetooth, and add region and chassis.
    new_db = copy.deepcopy(db)
    hwid_utils.UpdateDatabase(
        self.output_path, None, new_db, 'DVT',
        add_default_comp=None, del_comp=['bluetooth'],
        region=['us'], chassis=['NEW'])
    database.Database.LoadFile(self.output_path, verify_checksum)
    # Check the value.
    self.assertEquals(new_db['board'], 'CHROMEBOOK')
    self.assertEquals(new_db['image_id'], {0: 'EVT', 1: 'DVT'})
    self.assertNotIn({'bluetooth_field': 0}, new_db['pattern'][1]['fields'])
    self.assertIn({'region': 'us'},
                  new_db['encoded_fields']['region_field'].values())
    self.assertIn('NEW', new_db['components']['chassis']['items'])
    self.assertIn({'chassis': 'NEW'},
                  new_db['encoded_fields']['chassis_field'].values())

  def testBuildDatabaseMissingEssentailComponent(self):
    """Tests the essential component is missing at the probe result."""
    # Essential component 'board_version' is missing in probed result.
    probed_result = copy.deepcopy(self.probed_results[0])
    del probed_result['found_probe_value_map']['board_version']

    # Deleting the essential component is not allowed.
    with self.assertRaises(ValueError):
      hwid_utils.BuildDatabase(
          self.output_path, probed_result, 'CHROMEBOOK', 'EVT',
          del_comp=['board_version'])

    # Enter "y" to create a default item, or use add_default_comp argument.
    expected = {
        'board_version_default': {
            'default': True,
            'status': 'unqualified',
            'values': None}}
    with mock.patch('__builtin__.raw_input', return_value='y'):
      hwid_utils.BuildDatabase(
          self.output_path, probed_result, 'CHROMEBOOK', 'EVT')
    with open(self.output_path, 'r') as f:
      db = yaml.load(f.read())
    self.assertEquals(db['components']['board_version']['items'], expected)
    hwid_utils.BuildDatabase(
        self.output_path, probed_result, 'CHROMEBOOK', 'EVT',
        add_default_comp=['board_version'])
    with open(self.output_path, 'r') as f:
      db = yaml.load(f.read())
    self.assertEquals(db['components']['board_version']['items'], expected)

    # Enter "n" to create a default item, or use add_null_comp argument.
    with mock.patch('__builtin__.raw_input', return_value='n'):
      hwid_utils.BuildDatabase(
          self.output_path, probed_result, 'CHROMEBOOK', 'EVT')
    with open(self.output_path, 'r') as f:
      db = yaml.load(f.read())
    self.assertEquals(db['components']['board_version']['items'], {})
    self.assertEquals(db['encoded_fields']['board_version_field'],
                      {0: {'board_version': None}})
    hwid_utils.BuildDatabase(
        self.output_path, probed_result, 'CHROMEBOOK', 'EVT',
        add_null_comp=['board_version'])
    with open(self.output_path, 'r') as f:
      db = yaml.load(f.read())
    self.assertEquals(db['components']['board_version']['items'], {})
    self.assertEquals(db['encoded_fields']['board_version_field'],
                      {0: {'board_version': None}})

  def testDeprecateDefaultItem(self):
    """Tests the default item should be deprecated after adding a item."""
    probed_result = copy.deepcopy(self.probed_results[0])
    del probed_result['found_probe_value_map']['board_version']
    hwid_utils.BuildDatabase(
        self.output_path, probed_result, 'CHROMEBOOK', 'EVT',
        add_default_comp=['board_version'])
    with open(self.output_path, 'r') as f:
      db = yaml.load(f.read())
    self.assertEquals(
        db['components']['board_version']['items']['board_version_default'],
        {'default': True,
         'status': 'unqualified',
         'values': None})
    hwid_utils.UpdateDatabase(self.output_path, self.probed_results[0], db)
    self.assertEquals(
        db['components']['board_version']['items']['board_version_default'],
        {'default': True,
         'status': 'unsupported',
         'values': None})


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
