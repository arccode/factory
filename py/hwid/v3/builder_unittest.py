#!/usr/bin/python -u
# -*- coding: utf-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=protected-access

import copy
import os
import unittest
import mock
import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import builder
from cros.factory.hwid.v3 import yaml_tags
from cros.factory.utils import yaml_utils


TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


class BuilderMethodTest(unittest.TestCase):

  def testFilterSpecialCharacter(self):
    function = builder._FilterSpecialCharacter
    self.assertEquals(function(''), 'unknown')
    self.assertEquals(function('foo  bar'), 'foo_bar')
    self.assertEquals(function('aaa::bbb-ccc'), 'aaa_bbb_ccc')
    self.assertEquals(function('  aaa::bbb-ccc___'), 'aaa_bbb_ccc')

  def testPromptAndAsk(self):
    function = builder.PromptAndAsk
    with mock.patch('__builtin__.raw_input', return_value='') as mock_input:
      self.assertTrue(function('This is the question.', default_answer=True))
      mock_input.assert_called_once_with('This is the question. [Y/n] ')

    with mock.patch('__builtin__.raw_input', return_value='') as mock_input:
      self.assertFalse(function('This is the question.', default_answer=False))
      mock_input.assert_called_once_with('This is the question. [y/N] ')

    with mock.patch('__builtin__.raw_input', return_value='y'):
      self.assertTrue(function('This is the question.', default_answer=True))
      self.assertTrue(function('This is the question.', default_answer=False))

    with mock.patch('__builtin__.raw_input', return_value='n'):
      self.assertFalse(function('This is the question.', default_answer=True))
      self.assertFalse(function('This is the question.', default_answer=False))

  def testChecksumUpdater(self):
    # TODO(akahuang): Fix it in non-chroot.
    self.assertIsNotNone(builder.ChecksumUpdater())


class DatabaseBuilderTest(unittest.TestCase):

  def setUp(self):
    yaml_utils.ParseMappingAsOrderedDict()

    with open(os.path.join(TEST_DATA_PATH, 'test_db_builder.yaml'), 'r') as f:
      self.test_dbs = list(yaml.load_all(f.read()))

  def tearDown(self):
    yaml_utils.ParseMappingAsOrderedDict(False)

  def testInit(self):
    with self.assertRaises(ValueError):
      builder.DatabaseBuilder()
    db_builder = builder.DatabaseBuilder(db=self.test_dbs[0])
    db_builder = builder.DatabaseBuilder(board='CHROMEBOOK')
    self.assertEquals(db_builder.db['board'], 'CHROMEBOOK')

  def testGetLatestPattern(self):
    db_builder = builder.DatabaseBuilder(board='CHROMEBOOK')
    self.assertEquals(db_builder.GetLatestPattern(), None)
    db_builder = builder.DatabaseBuilder(db=self.test_dbs[0])
    latest_pattern = db_builder.GetLatestPattern()
    self.assertEquals(latest_pattern['image_ids'], [0, 1])

  def testGetLatestFields(self):
    db_builder = builder.DatabaseBuilder(board='CHROMEBOOK')
    self.assertEquals(db_builder.GetLatestFields(), set())
    db_builder = builder.DatabaseBuilder(db=self.test_dbs[0])
    self.assertEquals(db_builder.GetLatestFields(),
                      set(['region_field', 'chassis_field',
                           'audio_codec_field', 'battery_field',
                           'bluetooth_field', 'cellular_field',
                           'cpu_field', 'display_panel_field', 'dram_field',
                           'video_field', 'storage_field',
                           'firmware_keys_field', 'ro_main_firmware_field',
                           'ro_ec_firmware_field']))

  def testGetUnprobeableComponents(self):
    db_builder = builder.DatabaseBuilder(board='CHROMEBOOK')
    self.assertEquals(db_builder.GetUnprobeableComponents(), [])
    db_builder = builder.DatabaseBuilder(db=self.test_dbs[0])
    self.assertEquals(db_builder.GetUnprobeableComponents(),
                      ['display_panel'])

  def testAddDefaultComponent(self):
    db_builder = builder.DatabaseBuilder(board='CHROMEBOOK')
    old_db = copy.deepcopy(db_builder.db)
    db_builder.AddDefaultComponent('foo')
    for key in old_db:
      if key not in ['components', 'encoded_fields']:
        self.assertEquals(old_db[key], db_builder.db[key])
    self.assertEquals(db_builder.db['components'],
                      {'foo': {
                          'items': {
                              'foo_default': {
                                  'default': True,
                                  'status': 'unqualified',
                                  'values': None}}}})
    self.assertEquals(db_builder.db['encoded_fields'],
                      {'foo_field': {
                          0: {'foo': 'foo_default'}}})
    self.assertIn('foo_field', db_builder.active_fields)

    db_builder = builder.DatabaseBuilder(db=self.test_dbs[0])
    with self.assertRaises(Exception):
      db_builder.AddDefaultComponent('audio_codec')

  def testAddComponent(self):
    db_builder = builder.DatabaseBuilder(board='CHROMEBOOK')
    old_db = copy.deepcopy(db_builder.db)
    # Add a new component item.
    name = db_builder.AddComponent('foo', {'compact_str': 'FOO_0'}, 'foo_0')
    self.assertEquals(name, 'foo_0')
    for key in old_db:
      if key not in ['components']:
        self.assertEquals(old_db[key], db_builder.db[key])
    self.assertEquals(db_builder.db['components'],
                      {'foo': {
                          'items': {
                              'foo_0': {
                                  'status': 'unqualified',
                                  'values': {'compact_str': 'FOO_0'}}}}})

    # Add a component item which already exists.
    # Should return the original name.
    name = db_builder.AddComponent('foo', {'compact_str': 'FOO_0'}, 'foo_1')
    self.assertEquals(name, 'foo_0')
    self.assertEquals(db_builder.db['components'],
                      {'foo': {
                          'items': {
                              'foo_0': {
                                  'status': 'unqualified',
                                  'values': {'compact_str': 'FOO_0'}}}}})

    # Add a new component item with same name.
    # Should choose a different name.
    name = db_builder.AddComponent('foo', {'compact_str': 'FOO_2'}, 'foo_0')
    self.assertNotEquals(name, 'foo_0')
    self.assertEquals(db_builder.db['components'],
                      {'foo': {
                          'items': {
                              'foo_0': {
                                  'status': 'unqualified',
                                  'values': {'compact_str': 'FOO_0'}},
                              name: {
                                  'status': 'unqualified',
                                  'values': {'compact_str': 'FOO_2'}}}}})

    # Add a new component item with extra fields. It should match the original
    # one instead of adding a new one.
    name = db_builder.AddComponent('foo', {'compact_str': 'FOO_0',
                                           'extra_attr': 'LALA'}, 'foo_3')
    self.assertEquals(name, 'foo_0')

  def testAddFirmware(self):
    db_builder = builder.DatabaseBuilder(db=self.test_dbs[0])
    db_comp_items = db_builder.db['components']['ro_main_firmware']['items']
    db_builder.AddComponent('ro_main_firmware',
                            {'version': 'ro_main_firmware_2'})
    # Set old firmwares deprecated.
    self.assertEquals(
        db_comp_items['ro_main_firmware_0'].get('status', 'supported'),
        'deprecated')
    self.assertEquals(
        db_comp_items['ro_main_firmware_1'].get('status', 'supported'),
        'deprecated')
    self.assertEquals(
        db_comp_items['ro_main_firmware_2'].get('status', 'supported'),
        'unqualified')

  def testDeleteComponentClass(self):
    db_builder = builder.DatabaseBuilder(db=self.test_dbs[0])
    db_builder.DeleteComponentClass('audio_codec')
    self.assertNotIn('audio_codec_field', db_builder.active_fields)
    self.assertFalse(db_builder.db['components']['audio_codec']['probeable'])

    # Nothing happens when deleting a non-existed component.
    db_builder.DeleteComponentClass('foo')

  def testAddEncodedField(self):
    db_builder = builder.DatabaseBuilder(board='CHROMEBOOK')
    name = db_builder.AddComponent('foo', {'compact_str': 'FOO_0'}, 'foo_0')
    idx = db_builder.AddEncodedField('foo', name)
    self.assertEquals(idx, 0)
    idx = db_builder.AddEncodedField('foo', name)
    self.assertEquals(idx, 0)
    name1 = db_builder.AddComponent('foo', {'compact_str': 'FOO_1'}, 'foo_1')
    name2 = db_builder.AddComponent('foo', {'compact_str': 'FOO_2'}, 'foo_2')
    idx = db_builder.AddEncodedField('foo', [name1, name2])
    self.assertEquals(idx, 1)
    idx = db_builder.AddEncodedField('foo', [name1, name2])
    self.assertEquals(idx, 1)
    idx = db_builder.AddEncodedField('foo', [name2, name1])
    self.assertEquals(idx, 1)
    idx = db_builder.AddEncodedField('foo', [name1, name1])
    self.assertEquals(idx, 2)
    idx = db_builder.AddEncodedField('foo', [name1, name1, name1])
    self.assertEquals(idx, 3)

    with self.assertRaises(ValueError):
      idx = db_builder.AddEncodedField('foo', 'INVALID_NAME')
    with self.assertRaises(ValueError):
      idx = db_builder.AddEncodedField('foo', ['INVALID_NAME', name1])

    # Add a non-existed componenet item.
    with self.assertRaises(ValueError):
      idx = db_builder.AddEncodedField('foo', 'INVALID_NAME')

  def testIsNewPatternNeeded(self):  # pylint: disable=
    # New database with no existed pattern.
    db_builder = builder.DatabaseBuilder(board='CHROMEBOOK')
    self.assertTrue(db_builder._IsNewPatternNeeded(True))
    with self.assertRaises(ValueError):
      db_builder._IsNewPatternNeeded(False)

    # Delete a existed component from database.
    db_builder = builder.DatabaseBuilder(db=copy.deepcopy(self.test_dbs[0]))
    self.assertFalse(db_builder._IsNewPatternNeeded(True))
    self.assertFalse(db_builder._IsNewPatternNeeded(False))

    db_builder.DeleteComponentClass('audio_codec')
    self.assertTrue(db_builder._IsNewPatternNeeded(True))
    with self.assertRaises(ValueError):
      db_builder._IsNewPatternNeeded(False)

    # Add a new component into database.
    db_builder = builder.DatabaseBuilder(db=copy.deepcopy(self.test_dbs[0]))
    db_builder.AddDefaultComponent('FAKE_COMPONENT')
    self.assertTrue(db_builder._IsNewPatternNeeded(True))
    # The user confirms to add the new component into the existed pattern.
    with mock.patch('__builtin__.raw_input', return_value='y'):
      self.assertFalse(db_builder._IsNewPatternNeeded(False))
    # The user does not confirm to add the new component.
    with mock.patch('__builtin__.raw_input', return_value='n'):
      with self.assertRaises(ValueError):
        db_builder._IsNewPatternNeeded(False)

  def testConvertLegacyField(self):
    """Tests the conversion of legacy region and customization_id."""
    db_builder = builder.DatabaseBuilder(db=self.test_dbs[1])

    # Check the new style region encoded_field is created.
    self.assertIn('new_region_field', db_builder.active_fields)
    self.assertNotIn('region_field', db_builder.active_fields)
    self.assertIn('region_field', db_builder.db['encoded_fields'].keys())
    self.assertIn('new_region_field', db_builder.db['encoded_fields'].keys())
    self.assertEquals(
        set(db_builder.db['encoded_fields']['new_region_field'].GetRegions()),
        set(['us', 'gb', 'ca.hybrid']))
    # Check the old style region encoded_field is not active.
    self.assertNotIn('region_field', db_builder.active_fields)
    self.assertEquals(db_builder.db['pattern'][0]['fields'][0],
                      {'region_field': 8})
    rule_names = [rule['name'] for rule in db_builder.db['rules']]
    self.assertNotIn('verify.regions', rule_names)

    # Check the rules for region is removed.
    rule_names = [rule['name'] for rule in db_builder.db['rules']]
    self.assertNotIn('verify.regions', rule_names)

  def testConvertLegacyRegionWithoutRule(self):
    """Test the converting legacy region without rule."""
    db_builder = builder.DatabaseBuilder(db=self.test_dbs[2])
    self.assertIn('new_region_field', db_builder.active_fields)
    self.assertEquals(
        db_builder.db['encoded_fields']['new_region_field'].GetRegions(),
        ['us'])
    db_builder.AddRegions(['tw', 'jp'])
    self.assertIsInstance(
        db_builder.db['components']['region'], yaml_tags.RegionComponent)
    self.assertEquals(
        db_builder.db['encoded_fields']['new_region_field'].GetRegions(),
        ['us', 'tw', 'jp'])

  def testSplitEncodedField(self):
    """Test splitting the firmware field into multiple field."""
    db_builder = builder.DatabaseBuilder(db=self.test_dbs[4])
    # hash_gbb is ignored. key_recovery and key_root should be updated by the
    # probed result so they are also ignored.
    self.assertEquals(db_builder.active_fields,
                      {'ro_ec_firmware_field', 'ro_main_firmware_field'})
    self.assertEquals(db_builder.db['encoded_fields']['ro_ec_firmware_field'],
                      {0: {'ro_ec_firmware': 'ro_ec_firmware_0'},
                       1: {'ro_ec_firmware': 'ro_ec_firmware_1'}})
    self.assertEquals(db_builder.db['encoded_fields']['ro_main_firmware_field'],
                      {0: {'ro_main_firmware': 'ro_main_firmware_0'},
                       1: {'ro_main_firmware': 'ro_main_firmware_1'}})

  def testAddRegions(self):
    """Test the AddRegions method."""
    db_builder = builder.DatabaseBuilder(board='CHROMEBOOK')
    db_builder.AddRegions(['tw', 'jp'])
    self.assertIsInstance(
        db_builder.db['components']['region'], yaml_tags.RegionComponent)
    self.assertEquals(
        db_builder.db['encoded_fields']['region_field'].GetRegions(),
        ['tw', 'jp'])

  def testAddChassis(self):
    # Add chassis to an empty database.
    db_builder = builder.DatabaseBuilder(board='CHROMEBOOK')
    db_builder.AddChassis(['FOO', 'BAR'])
    self.assertEquals(
        db_builder.db['components']['chassis']['items'], {
            'FOO': {
                'status': 'unqualified',
                'values': {'id': 'FOO'}},
            'BAR': {
                'status': 'unqualified',
                'values': {'id': 'BAR'}}})
    self.assertEquals(
        db_builder.db['encoded_fields']['chassis_field'],
        {0: {'chassis': 'FOO'},
         1: {'chassis': 'BAR'}})
    self.assertTrue(
        db_builder.db['components']['chassis'].get('probeable', True))

    # Add a new chassis and ignore the repeated one.
    db_builder.AddChassis(['FOO', 'NEW'])
    self.assertEquals(
        db_builder.db['components']['chassis']['items'], {
            'FOO': {
                'status': 'unqualified',
                'values': {'id': 'FOO'}},
            'BAR': {
                'status': 'unqualified',
                'values': {'id': 'BAR'}},
            'NEW': {
                'status': 'unqualified',
                'values': {'id': 'NEW'}}})
    self.assertEquals(
        db_builder.db['encoded_fields']['chassis_field'],
        {0: {'chassis': 'FOO'},
         1: {'chassis': 'BAR'},
         2: {'chassis': 'NEW'}})
    self.assertTrue(
        db_builder.db['components']['chassis'].get('probeable', True))

  def testVerify(self):
    db_builder = builder.DatabaseBuilder(db=self.test_dbs[0])
    db_builder.Verify()

    # Repeated image_id.
    origin = copy.deepcopy(db_builder.db['image_id'])
    db_builder.db['image_id'][2] = 'DVT'
    with self.assertRaisesRegexp(ValueError, 'image_id "DVT" is repeated.'):
      db_builder.Verify()
    db_builder.db['image_id'] = origin
    # Invalid image_id index.
    origin = copy.deepcopy(db_builder.db['image_id'])
    db_builder.db['image_id'][16] = 'DVT'
    with self.assertRaisesRegexp(
        ValueError, r'image_id index \[16\] are invalid.'):
      db_builder.Verify()
    db_builder.db['image_id'] = origin
    # image_id without pattern.
    origin = copy.deepcopy(db_builder.db['image_id'])
    db_builder.db['image_id'][2] = 'PVT'
    with self.assertRaisesRegexp(
        ValueError, r'image_id index \[2\] are missing in the pattern.'):
      db_builder.Verify()
    db_builder.db['image_id'] = origin

    # Unknown image_id in the pattern.
    origin = copy.deepcopy(db_builder.db['pattern'])
    db_builder.db['pattern'][0]['image_ids'].append(2)
    with self.assertRaisesRegexp(
        ValueError, r'Unknown image_id "2" appears in pattern.'):
      db_builder.Verify()
    db_builder.db['pattern'] = origin
    # Repeated image_id in multiple patterns.
    origin = copy.deepcopy(db_builder.db['pattern'])
    db_builder.db['pattern'].append({
        'image_ids': [1],
        'encoding_scheme': 'base8192',
        'fields': []})
    with self.assertRaisesRegexp(
        ValueError, r'image_id "1" appears in pattern repeatedly.'):
      db_builder.Verify()
    db_builder.db['pattern'] = origin
    # Region field is missing in the pattern.
    origin = copy.deepcopy(db_builder.db['pattern'])
    db_builder.db['pattern'][0]['fields'].pop(0)
    with self.assertRaisesRegexp(
        ValueError, r'\[region_field\] are missing in current pattern.'):
      db_builder.Verify()
    db_builder.db['pattern'] = origin
    # foo_fields is extra in the pattern.
    origin = copy.deepcopy(db_builder.db['pattern'])
    db_builder.db['pattern'][0]['fields'].append({'foo_field': 0})
    with self.assertRaisesRegexp(
        ValueError, r'\[foo_field\] are extra fields in current pattern.'):
      db_builder.Verify()
    db_builder.db['pattern'] = origin
    # Region field does not have enough bit field.
    origin = copy.deepcopy(db_builder.db['pattern'])
    db_builder.db['pattern'][0]['fields'][0] = {'region_field': 0}
    with self.assertRaisesRegexp(
        ValueError, r'The bit size of "region_field" is not enough.'):
      db_builder.Verify()
    db_builder.db['pattern'] = origin

  def testUpdatePattern(self):
    db_builder = builder.DatabaseBuilder(db=self.test_dbs[3])
    # Originally cpu_field has 2 bits for 4 components. Should add one more bit
    # after adding a new component.
    comp_name = db_builder.AddComponent('cpu', {'name': 'NEW CPU', 'cores': 64})
    db_builder.AddEncodedField('cpu', comp_name)
    db_builder._UpdatePattern(2)
    self.assertEquals(db_builder.db['pattern'][0]['image_ids'], [0, 1, 2])
    self.assertEquals(db_builder.db['pattern'][0]['fields'],
                      [{'cpu_field': 1}, {'cpu_field': 1}, {'cpu_field': 1}])

  def testAddPattern(self):
    origin_db = self.test_dbs[5]
    db_builder = builder.DatabaseBuilder(db=origin_db)
    # Add region and ro_main_firmware.
    db_builder.AddRegions(['us', 'tw'])
    comp_name = db_builder.AddComponent('ro_main_firmware',
                                        {'version': 'RO_MAIN_0'})
    db_builder.AddEncodedField('ro_main_firmware', comp_name)

    db_builder._AddPattern(2)
    self.assertEquals(db_builder.db['pattern'][0]['image_ids'],
                      origin_db['pattern'][0]['image_ids'])
    self.assertEquals(db_builder.db['pattern'][0]['fields'],
                      origin_db['pattern'][0]['fields'])
    self.assertEquals(db_builder.db['pattern'][1]['image_ids'], [2])
    self.assertEquals(db_builder.db['pattern'][1]['fields'],
                      [{'board_version_field': 3},
                       {'region_field': 5},
                       {'chassis_field': 5},
                       {'cpu_field': 3},
                       {'storage_field': 5},
                       {'dram_field': 5},
                       {'ro_main_firmware_field': 3}])


if __name__ == '__main__':
  unittest.main()
