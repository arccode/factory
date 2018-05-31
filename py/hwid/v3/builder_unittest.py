#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import builder
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import probe
from cros.factory.utils import file_utils


_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')
_TEST_DATABASE_PATH = os.path.join(_TEST_DATA_PATH, 'test_builder_db.yaml')


class DetermineComponentNameTest(unittest.TestCase):

  def testMainboard(self):
    comp_cls = 'mainboard'
    value = {
        'version': 'rev2'}
    expected = 'rev2'
    self.assertEquals(expected, builder.DetermineComponentName(comp_cls, value))

  def testFirmwareKeys(self):
    comp_cls = 'firmware_keys'
    value = {
        'key_recovery':
            'c14bd720b70d97394257e3e826bd8f43de48d4ed#devkeys/recovery',
        'key_root': 'b11d74edd286c144e1135b49e7f0bc20cf041f10#devkeys/rootkey'}
    expected = 'firmware_keys_dev'
    self.assertEquals(expected, builder.DetermineComponentName(comp_cls, value))

  def testDRAM(self):
    comp_cls = 'dram'
    value = {
        'part': 'ABCD',
        'size': '2048',
        'slot': '0',
        'timing': 'DDR3-800,DDR3-1066,DDR3-1333,DDR3-1600'}
    expected = 'ABCD_2048mb_0'
    self.assertEquals(expected, builder.DetermineComponentName(comp_cls, value))


class BuilderMethodTest(unittest.TestCase):

  def testFilterSpecialCharacter(self):
    function = builder.FilterSpecialCharacter
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
    checksum_updater = builder.ChecksumUpdater()
    self.assertIsNotNone(checksum_updater)
    with open(os.path.join(_TEST_DATA_PATH, 'CHECKSUM_TEST'), 'r') as f:
      checksum_test = f.read()
    updated = checksum_updater.ReplaceChecksum(checksum_test)
    with open(os.path.join(_TEST_DATA_PATH, 'CHECKSUM_TEST.golden'), 'r') as f:
      checksum_test_golden = f.read()
    self.assertEquals(updated, checksum_test_golden)


class DatabaseBuilderTest(unittest.TestCase):

  def testInit(self):
    self.assertRaises(ValueError, builder.DatabaseBuilder)

    # From file.
    db = builder.DatabaseBuilder(database_path=_TEST_DATABASE_PATH)
    self.assertEquals(db.database,
                      Database.LoadFile(_TEST_DATABASE_PATH,
                                        verify_checksum=False))

    # From stratch.
    self.assertRaises(ValueError, builder.DatabaseBuilder, project='PROJ')

    db = builder.DatabaseBuilder(project='PROJ', image_name='PROTO')
    self.assertEquals(db.database.project, 'PROJ')
    self.assertEquals(db.database.GetImageName(0), 'PROTO')

  def testAddDefaultComponent(self):
    db = builder.DatabaseBuilder(database_path=_TEST_DATABASE_PATH)

    db.AddDefaultComponent('comp_cls_1')

    # If the probed results don't contain the component value, the default
    # component should be returned.
    bom = probe.GenerateBOMFromProbedResults(
        db.database, {}, {}, {}, 'normal', False)[0]
    self.assertEquals(bom.components['comp_cls_1'], ['comp_cls_1_default'])

    # If the probed results contain a real component value, the default
    # component shouldn't be returned.
    bom = probe.GenerateBOMFromProbedResults(
        db.database,
        {'comp_cls_1': [{'name': 'comp1', 'values': {'value': "1"}}]},
        {}, {}, 'normal', False)[0]
    self.assertEquals(bom.components['comp_cls_1'], ['comp_1_1'])

    # One component class can have at most one default component.
    self.assertRaises(ValueError, db.AddDefaultComponent, 'comp_cls_1')

  def testAddNullComponent(self):
    db = builder.DatabaseBuilder(database_path=_TEST_DATABASE_PATH)

    db.AddNullComponent('comp_cls_1')
    self.assertEquals({0: {'comp_cls_1': ['comp_1_1']},
                       1: {'comp_cls_1': ['comp_1_2']},
                       2: {'comp_cls_1': []}},
                      db.database.GetEncodedField('comp_cls_1_field'))

    # The database already accepts a device without a cpu component.
    db.AddNullComponent('cpu')
    self.assertEquals(
        {0: {'cpu': []}}, db.database.GetEncodedField('cpu_field'))

    # The given component class was not recorded in the database.
    db.AddNullComponent('new_component')
    self.assertEquals({0: {'new_component': []}},
                      db.database.GetEncodedField('new_component_field'))

    # Should fail if the encoded field of the specified component class encodes
    # more than one class of components.
    self.assertRaises(ValueError, db.AddNullComponent, 'comp_cls_2')

  @mock.patch('cros.factory.hwid.v3.builder.PromptAndAsk',
              return_value=False)
  def testUpdateByProbedResultsAddFirmware(self, unused_prompt_and_ask_mock):
    db = builder.DatabaseBuilder(database_path=_TEST_DATABASE_PATH)
    db.UpdateByProbedResults(
        {'ro_main_firmware': [{'name': 'generic', 'values': {'hash': '1'}}]},
        {}, {})

    # Should deprecated the legacy firmwares.
    self.assertEquals(
        db.database.GetComponents('ro_main_firmware')['firmware0'].status,
        common.COMPONENT_STATUS.deprecated)

  @mock.patch('cros.factory.hwid.v3.builder.PromptAndAsk')
  def testUpdateByProbedResultsWithExtraComponentClasses(self,
                                                         prompt_and_ask_mock):
    for add_null_comp in [False, True]:
      prompt_and_ask_mock.return_value = add_null_comp

      db = builder.DatabaseBuilder(database_path=_TEST_DATABASE_PATH)
      db.UpdateByProbedResults(
          {'comp_cls_100': [{'name': 'generic', 'values': {'key1': 'value1'}},
                            {'name': 'generic', 'values': {'key1': 'value1',
                                                           'key2': 'value2'}},
                            {'name': 'generic', 'values': {'key1': 'value1',
                                                           'key3': 'value3'}},
                            {'name': 'special', 'values': {'key4': 'value4'}},
                            {'name': 'special', 'values': {'key4': 'value5'}}]},
          {}, {}, image_name='NEW_IMAGE')
      self.assertEquals(
          sorted([attr.values for attr in db.database.GetComponents(
              'comp_cls_100').itervalues()]),
          sorted([{'key1': 'value1'}, {'key4': 'value4'}, {'key4': 'value5'}]))

      self.assertEquals(
          add_null_comp,
          {'comp_cls_100': []} in db.database.GetEncodedField(
              'comp_cls_100_field').values())

  @mock.patch('cros.factory.hwid.v3.builder.PromptAndAsk', return_value=False)
  def testUpdateByProbedResultsWithExtraComponents(
      self, unused_prompt_and_ask_mock):
    db = builder.DatabaseBuilder(database_path=_TEST_DATABASE_PATH)

    # {'value': '3'} is the extra component.
    db.UpdateByProbedResults(
        {'comp_cls_1': [{'name': 'generic', 'values': {'value': '1'}},
                        {'name': 'generic', 'values': {'value': '3'}}]}, {}, {},
        image_name='NEW_IMAGE')
    self.assertEquals(
        sorted([attr.values for attr in db.database.GetComponents(
            'comp_cls_1').itervalues()]),
        sorted([{'value': '1'}, {'value': '2'}, {'value': '3'}]))

    self.assertIn({'comp_cls_1': sorted(['comp_1_1', '3'])},
                  db.database.GetEncodedField('comp_cls_1_field').values())

  @mock.patch('cros.factory.hwid.v3.builder.PromptAndAsk')
  def testUpdateByProbedResultsMissingEssentialComponents(self,
                                                          prompt_and_ask_mock):
    # If the user answer "N", the null component will be added.
    prompt_and_ask_mock.return_value = False
    db = builder.DatabaseBuilder(database_path=_TEST_DATABASE_PATH)
    db.UpdateByProbedResults({}, {}, {}, image_name='NEW_IMAGE')
    for comp_cls in builder.ESSENTIAL_COMPS:
      self.assertIn({comp_cls: []},
                    db.database.GetEncodedField(comp_cls + '_field').values())

    # If the user answer "Y", the default component will be added if no null
    # component is recorded.
    prompt_and_ask_mock.return_value = True
    db = builder.DatabaseBuilder(database_path=_TEST_DATABASE_PATH)
    db.UpdateByProbedResults({}, {}, {}, image_name='NEW_IMAGE')
    for comp_cls in builder.ESSENTIAL_COMPS:
      if {comp_cls: []} in db.database.GetEncodedField(
          comp_cls + '_field').values():
        continue
      self.assertIn(comp_cls + '_default', db.database.GetComponents(comp_cls))
      self.assertIn({comp_cls: [comp_cls + '_default']},
                    db.database.GetEncodedField(comp_cls + '_field').values())

  @mock.patch('cros.factory.hwid.v3.builder.PromptAndAsk', return_value=False)
  def testUpdateByProbedResultsUpdateEncodedFieldsAndPatternCorrectly(
      self, unused_prompt_and_ask_mock):
    db = builder.DatabaseBuilder(database_path=_TEST_DATABASE_PATH)

    # Add a lot of mainboard so that the field need more bits.
    for i in xrange(10):
      db.UpdateByProbedResults(
          {'mainboard': [{'name': 'generic', 'values': {'rev': str(i)}}]},
          {}, {})

    # Add a lot of cpu so that the field need more bits.
    for i in xrange(50):
      db.UpdateByProbedResults(
          {'cpu': [{'name': 'generic', 'values': {'vendor': str(i)}}]}, {}, {})

    # Add more component combination of comp_cls_1, comp_cls_2 and comp_cls_3.
    # Also add an extran component class to trigger adding a new pattern.
    db.UpdateByProbedResults(
        {'comp_cls_1': [{'name': 'generic', 'values': {'value': '1'}},
                        {'name': 'generic', 'values': {'value': '3'}}],
         'comp_cls_2': [{'name': 'generic', 'values': {'value': '2'}}],
         'comp_cls_3': [{'name': 'generic', 'values': {'value': '1'}}],
         'comp_cls_100': [{'name': 'generic', 'values': {'value': '100'}}]},
        {}, {}, image_name='NEW_IMAGE')

    self.assertEquals(
        db.database.GetEncodedField('comp_cls_23_field'),
        {0: {'comp_cls_2': ['comp_2_1'], 'comp_cls_3': ['comp_3_1']},
         1: {'comp_cls_2': ['comp_2_2'], 'comp_cls_3': ['comp_3_2']},
         2: {'comp_cls_2': [], 'comp_cls_3': []},
         3: {'comp_cls_2': ['comp_2_2'], 'comp_cls_3': ['comp_3_1']}})

    # Check the pattern by checking if the fields bit length are all correct.
    self.assertEquals(db.database.GetEncodedFieldsBitLength(),
                      {'mainboard_field': 8,
                       'region_field': 5,
                       'chassis_field': 3,
                       'cpu_field': 10,
                       'storage_field': 3,
                       'dram_field': 5,
                       'firmware_keys_field': 1,
                       'ro_main_firmware_field': 3,
                       'comp_cls_1_field': 2,
                       'comp_cls_23_field': 2,
                       'comp_cls_100_field': 0})

  @mock.patch('cros.factory.hwid.v3.builder.PromptAndAsk', return_value=False)
  def testUpdateByProbedResultsNoNeedNewPattern(
      self, unused_prompt_and_ask_mock):
    # No matter if new image name is specified, the pattern will always use
    # the same one if no new encoded fields are added.
    for image_name in [None, 'EVT', 'NEW_IMAGE_NAME']:
      db = builder.DatabaseBuilder(database_path=_TEST_DATABASE_PATH)
      db.UpdateByProbedResults(
          {'comp_cls_2': [{'name': 'generic', 'values': {str(x): str(x)}}
                          for x in xrange(10)]},
          {}, {}, image_name=image_name)
      self.assertEquals(db.database.GetBitMapping(0),
                        db.database.GetBitMapping(db.database.max_image_id))

  @mock.patch('cros.factory.hwid.v3.builder.PromptAndAsk', return_value=False)
  def testUpdateByProbedResultsNeedNewPattern(self, unused_prompt_and_ask_mock):
    # New pattern is required if new encoded fields are added.
    db = builder.DatabaseBuilder(database_path=_TEST_DATABASE_PATH)

    db.UpdateByProbedResults(
        {'comp_cls_200': [{'name': 'generic', 'values': {str(x): str(x)}}
                          for x in xrange(10)]},
        {}, {}, image_name='NEW_IMAGE_NAME')
    self.assertNotIn('comp_cls_200_field',
                     db.database.GetEncodedFieldsBitLength(0))
    self.assertIn('comp_cls_200_field',
                  db.database.GetEncodedFieldsBitLength())
    self.assertIn('NEW_IMAGE_NAME',
                  db.database.GetImageName(db.database.max_image_id))

    # Should raise error if new image is needed but no image name.
    db = builder.DatabaseBuilder(database_path=_TEST_DATABASE_PATH)
    self.assertRaises(ValueError, db.UpdateByProbedResults,
                      {'comp_cls_200': [{'name': 'x', 'values': {'a': 'b'}}]},
                      {}, {})

  def testRender(self):
    db = builder.DatabaseBuilder(database_path=_TEST_DATABASE_PATH)
    path = file_utils.CreateTemporaryFile()
    db.Render(path)

    # Should be able to load successfully and pass the checksum check.
    Database.LoadFile(path)


if __name__ == '__main__':
  unittest.main()
