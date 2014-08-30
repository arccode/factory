#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import os
import re
import shutil
import sys
import tempfile
import unittest
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import config
from cros.factory.umpire.common import UmpireError
from cros.factory.umpire.umpire_env import UmpireEnv
from cros.factory.utils import file_utils

TESTDATA_DIR = os.path.join(os.path.dirname(sys.modules[__name__].__file__),
                            'testdata')
MINIMAL_CONFIG = os.path.join(TESTDATA_DIR, 'minimal_umpire.yaml')
EMPTY_SERVICES_CONFIG = os.path.join(TESTDATA_DIR,
                                     'minimal_empty_services_umpire.yaml')
RESOURCE_CHECK_CONFIG = os.path.join(TESTDATA_DIR,
                                     'umpire_resource_check.yaml')
RULESET_CONFIG = os.path.join(TESTDATA_DIR, 'rulesets_umpire.yaml')

_RE_COMMENT = re.compile(r'\s*# .+')


class TestUmpireConfig(unittest.TestCase):
  def testLoadConfig(self):
    conf = config.UmpireConfig(EMPTY_SERVICES_CONFIG)
    self.assertEqual(1, len(conf['rulesets']))
    ruleset = conf['rulesets'][0]
    self.assertDictEqual(
        {'bundle_id': 'test',
         'note': 'ruleset for test',
         'active': True},
        ruleset)

    self.assertEqual(1, len(conf['bundles']))
    bundle = conf['bundles'][0]
    self.assertEqual('test', bundle['id'])
    self.assertEqual('bundle for test', bundle['note'])

  def testLoadConfigNotFound(self):
    self.assertRaises(IOError, config.UmpireConfig, '/path/to/no/where')

  def testLoadConfigFromDict(self):
    with open(EMPTY_SERVICES_CONFIG) as f:
      config_dict = yaml.load(f)
    conf = config.UmpireConfig(config_dict)
    self.assertEqual(1, len(conf['rulesets']))
    ruleset = conf['rulesets'][0]
    self.assertDictEqual(
        {'bundle_id': 'test',
         'note': 'ruleset for test',
         'active': True},
        ruleset)

    self.assertEqual(1, len(conf['bundles']))
    bundle = conf['bundles'][0]
    self.assertEqual('test', bundle['id'])
    self.assertEqual('bundle for test', bundle['note'])

  def testLoadConfigString(self):
    with open(EMPTY_SERVICES_CONFIG) as f:
      config_str = f.read()
    conf = config.UmpireConfig(config_str)
    self.assertEqual(1, len(conf['rulesets']))
    ruleset = conf['rulesets'][0]
    self.assertDictEqual(
        {'bundle_id': 'test',
         'note': 'ruleset for test',
         'active': True},
        ruleset)

    self.assertEqual(1, len(conf['bundles']))
    bundle = conf['bundles'][0]
    self.assertEqual('test', bundle['id'])
    self.assertEqual('bundle for test', bundle['note'])

  def testLoadConfigFromConfigDeepCopy(self):
    conf = config.UmpireConfig(EMPTY_SERVICES_CONFIG)
    original_complete_script = conf['bundles'][0]['resources'][
        'complete_script']

    dup_conf = config.UmpireConfig(conf)
    dup_conf['bundles'][0]['resources']['complete_script'] = (
        'new_complete.gz##d41d8cd9')

    # Make sure that the structure is deep-copied.
    self.assertEqual(original_complete_script,
                     conf['bundles'][0]['resources']['complete_script'])

  def testLoadConfigRuleMatcher(self):
    conf = config.UmpireConfig(RULESET_CONFIG)
    self.assertEqual(2, len(conf['rulesets']))
    ruleset = conf['rulesets'][0]
    self.assertDictEqual(
        {'bundle_id': 'test',
         'note': 'ruleset with matchers',
         'active': True,
         'match': {
             'mac': ['aa:bb:cc:dd:ee:ff'],
             'mlb_sn': ['SN001'],
             'mlb_sn_range': ['-', 'SN005'],
             'sn': ['OC1234567890'],
             'sn_range': ['OC1234567890', '-']},
          'enable_update': {
              'device_factory_toolkit': ['RUNIN', 'RUNIN'],
              'rootfs_release': ['SMT', 'SMT'],
              'rootfs_test': ['FA', 'FA'],
              'firmware_ec': ['GRT', 'GRT'],
              'firmware_bios': [None, None]}},
        ruleset)

    default_ruleset = conf['rulesets'][1]
    self.assertDictEqual(
        {'bundle_id': 'test',
         'note': 'ruleset for test',
         'active': True},
        default_ruleset)


  def testWriteConfig(self):
    def RemoveComments(lines):
      return [_RE_COMMENT.sub('', line) for line in lines]

    # TODO(deanliao): remove validate=False once services are implemented.
    conf = config.UmpireConfig(MINIMAL_CONFIG, validate=False)

    with file_utils.UnopenedTemporaryFile() as new_config_file:
      conf.WriteFile(new_config_file)

      # TODO(deanliao): remove this once we can dump comments.
      config_lines = RemoveComments(file_utils.ReadLines(MINIMAL_CONFIG))
      new_config_lines = file_utils.ReadLines(new_config_file)

      self.maxDiff = None
      self.assertListEqual(config_lines, new_config_lines)

  def testGetDefaultBundle(self):
    conf = config.UmpireConfig(EMPTY_SERVICES_CONFIG)
    self.assertEqual('test', conf.GetDefaultBundle()['id'])

    conf['rulesets'].append({'bundle_id': 'new_bundle',
                             'active': True})
    new_bundle = copy.deepcopy(conf['bundles'][0])
    new_bundle['id'] = 'new_bundle'
    conf['bundles'].append(new_bundle)
    conf.BuildBundleMap()
    self.assertEqual('new_bundle', conf.GetDefaultBundle()['id'])

    # Last ruleset is inactive, use the upper one.
    conf['rulesets'][1]['active'] = False
    self.assertEqual('test', conf.GetDefaultBundle()['id'])

  def testGetDefaultBundleNotFound(self):
    conf = config.UmpireConfig(EMPTY_SERVICES_CONFIG)

    # A default bundle ID derived from rulesets doesn't exist in bundles
    # section.
    conf['rulesets'].append({'bundle_id': 'new_bundle',
                             'active': True})
    self.assertIsNone(conf.GetDefaultBundle())

    # no active ruleset.
    conf['rulesets'][0]['active'] = False
    self.assertIsNone(conf.GetDefaultBundle())

    # no ruleset.
    del conf['rulesets'][:]
    self.assertIsNone(conf.GetDefaultBundle())

  def testGetBundle(self):
    conf = config.UmpireConfig(EMPTY_SERVICES_CONFIG)
    new_bundle = copy.deepcopy(conf['bundles'][0])
    new_bundle['id'] = 'new_bundle'
    new_bundle['note'] = 'new bundle for test'
    new_bundle['resources']['complete_script'] = 'complete.gz##00000001'
    conf['bundles'].append(new_bundle)
    conf.BuildBundleMap()

    bundle = conf.GetBundle('test')
    self.assertEqual('test', bundle['id'])
    self.assertEqual('bundle for test', bundle['note'])
    self.assertEqual('complete.gz##d41d8cd9',
                     bundle['resources']['complete_script'])

    bundle = conf.GetBundle('new_bundle')
    self.assertEqual('new_bundle', bundle['id'])
    self.assertEqual('new bundle for test', bundle['note'])
    self.assertEqual('complete.gz##00000001',
                     bundle['resources']['complete_script'])

    self.assertIsNone(conf.GetBundle('nonexist_bundle'))

  def testGetActiveBundles(self):
    conf = config.UmpireConfig(EMPTY_SERVICES_CONFIG)
    conf['rulesets'] = [
        {'bundle_id': 'id_1', 'active': True},
        {'bundle_id': 'id_2', 'active': False},
        {'bundle_id': 'id_3', 'active': True},
        {'bundle_id': 'id_5', 'active': True}]
    conf['bundles'] = [
        {'id': 'id_1', 'test_pass': True},
        {'id': 'id_2', 'test_pass': False},
        {'id': 'id_3', 'test_pass': True},
        {'id': 'id_4', 'test_pass': False}]
    conf.BuildBundleMap()
    for bundle in conf.GetActiveBundles():
      self.assertTrue(bundle['test_pass'])


class TestValidateResources(unittest.TestCase):
  def setUp(self):
    self.env = UmpireEnv()
    self.temp_dir = tempfile.mkdtemp()
    self.env.base_dir = self.temp_dir
    os.makedirs(self.env.resources_dir)
    self.conf = config.UmpireConfig(RESOURCE_CHECK_CONFIG, validate=False)

    self.hwid1 = self.MakeResourceFile('hwid.gz', 'hwid1')
    self.hwid2 = self.MakeResourceFile('hwid.gz', 'hwid2')
    self.MakeResourceFile('efi.gz', 'efi1')
    self.MakeResourceFile('efi.gz', 'efi2')

  def tearDown(self):
    if os.path.isdir(self.temp_dir):
      shutil.rmtree(self.temp_dir)

  def MakeResourceFile(self, filename, content):
    path = os.path.join(self.temp_dir, filename)
    file_utils.WriteFile(path, content)
    return self.env.AddResource(path)

  def testNormal(self):
    config.ValidateResources(self.conf, self.env)

  def testFileNotFound(self):
    # Resources in the second ruleset's bundle are not presented.
    self.conf['rulesets'][1]['active'] = True
    self.assertRaisesRegexp(UmpireError, 'NOT FOUND.+efi.gz##00000000',
                            config.ValidateResources, self.conf, self.env)

  def testFileNotFound2(self):
    def RenameResourceThenTest(resource_path):
      filename = os.path.basename(resource_path)
      temp_path = os.path.join(self.temp_dir, filename)
      os.rename(resource_path, temp_path)
      self.assertRaisesRegexp(UmpireError, 'NOT FOUND.+' + filename,
                              config.ValidateResources, self.conf, self.env)
      os.rename(temp_path, resource_path)

    # Remove hwid in the first and second active bundle, respectively.
    RenameResourceThenTest(self.hwid1)
    RenameResourceThenTest(self.hwid2)

  def testFileChechsumMismatch(self):
    file_utils.WriteFile(self.hwid1, 'content changed')
    self.assertRaisesRegexp(
        UmpireError, 'CHECKSUM MISMATCH.+hwid.gz##9c7de5c7',
        config.ValidateResources, self.conf, self.env)


class testShowDiff(unittest.TestCase):
  def testChangeBundle(self):
    original = {
        'rulesets': [
            {'bundle_id': 'original_bundle',
             'note': 'ruleset 1',
             'active': True}]}
    new = {
        'rulesets': [
            {'bundle_id': 'new_bundle',
             'note': 'ruleset 1',
             'active': True}]}
    self.assertListEqual(
        ['Newly added rulesets:',
         '  bundle_id: new_bundle',
         '  note: ruleset 1',
         '  active: true',
         '  ',
         'Deleted rulesets:',
         '  bundle_id: original_bundle',
         '  note: ruleset 1',
         '  active: true',
         '  '],
        config.ShowDiff(original, new))

  def testInactive(self):
    original = {
        'rulesets': [
            {'bundle_id': 'bundle_1',
             'note': 'ruleset 1',
             'active': True},
            {'bundle_id': 'bundle_2',
             'note': 'ruleset 2',
             'active': True}]}
    new = {
        'rulesets': [
            {'bundle_id': 'bundle_1',
             'note': 'ruleset 1',
             'active': False},
            {'bundle_id': 'bundle_2',
             'note': 'ruleset 2',
             'active': True}]}

    self.assertListEqual(
        ['Deleted rulesets:',
         '  bundle_id: bundle_1',
         '  note: ruleset 1',
         '  active: true',
         '  '],
        config.ShowDiff(original, new))

  def testActive(self):
    original = {
        'rulesets': [
            {'bundle_id': 'bundle_1',
             'note': 'ruleset 1 to active',
             'active': False},
            {'bundle_id': 'bundle_2',
             'note': 'ruleset 2',
             'active': True}]}
    new = {
        'rulesets': [
            {'bundle_id': 'bundle_1',
             'note': 'ruleset 1 active',
             'active': True},
            {'bundle_id': 'bundle_2',
             'note': 'ruleset 2',
             'active': True}]}

    self.assertListEqual(
        ['Newly added rulesets:',
         '  bundle_id: bundle_1',
         '  note: ruleset 1 active',
         '  active: true',
         '  '],
        config.ShowDiff(original, new))



if __name__ == '__main__':
  unittest.main()
