#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import os
import re
import unittest
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import common
from cros.factory.umpire.server import config
from cros.factory.umpire.server import resource
from cros.factory.umpire.server import umpire_env
from cros.factory.utils import file_utils

TESTDATA_DIR = os.path.join(os.path.dirname(__file__), 'testdata')
MINIMAL_CONFIG = os.path.join(TESTDATA_DIR, 'minimal_umpire.yaml')
EMPTY_SERVICES_CONFIG = os.path.join(TESTDATA_DIR,
                                     'minimal_empty_services_umpire.yaml')
RESOURCE_CHECK_CONFIG = os.path.join(TESTDATA_DIR,
                                     'umpire_resource_check.yaml')
RULESET_CONFIG = os.path.join(TESTDATA_DIR, 'rulesets_umpire.yaml')

_RE_COMMENT = re.compile(r'\s*# .+')


class UmpireConfigTest(unittest.TestCase):

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
    config_str = file_utils.ReadFile(EMPTY_SERVICES_CONFIG)
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
    original_payloads = conf['bundles'][0]['payloads']

    dup_conf = config.UmpireConfig(conf)
    dup_conf['bundles'][0]['payloads'] = 'new payloads'

    # Make sure that the structure is deep-copied.
    self.assertEqual(original_payloads, conf['bundles'][0]['payloads'])

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
             'sn_range': ['OC1234567890', '-'],
             'stage': ['SMT', 'FATP']},
         'enable_update': {
             'device_factory_toolkit': ['RUNIN', 'RUNIN'],
             'rootfs_release': ['SMT', 'SMT'],
             'rootfs_test': ['FA', 'FA'],
             'firmware_ec': ['GRT', 'GRT'],
             'firmware_pd': ['SMT', 'SMT'],
             'firmware_bios': [None, None]}},
        ruleset)

    default_ruleset = conf['rulesets'][1]
    self.assertDictEqual(
        {'bundle_id': 'test',
         'note': 'ruleset for test',
         'active': True},
        default_ruleset)

  def testDumpConfig(self):
    def RemoveComments(lines):
      return [_RE_COMMENT.sub('', line.rstrip()) for line in lines]

    # TODO(deanliao): remove validate=False once services are implemented.
    conf = config.UmpireConfig(MINIMAL_CONFIG, validate=False)
    new_config_lines = conf.Dump().splitlines()
    # TODO(deanliao): remove this once we can dump comments.
    config_lines = RemoveComments(file_utils.ReadLines(MINIMAL_CONFIG))

    self.maxDiff = None
    self.assertListEqual(config_lines, new_config_lines)

  def testGetDefaultBundle(self):
    conf = config.UmpireConfig(EMPTY_SERVICES_CONFIG)
    self.assertEqual('test', conf.GetDefaultBundle()['id'])

    conf['rulesets'].insert(0, {'bundle_id': 'new_bundle', 'active': True})
    new_bundle = copy.deepcopy(conf['bundles'][0])
    new_bundle['id'] = 'new_bundle'
    conf['bundles'].append(new_bundle)
    conf.BuildBundleMap()
    self.assertEqual('new_bundle', conf.GetDefaultBundle()['id'])

    # First ruleset is inactive, use the lower one.
    conf['rulesets'][0]['active'] = False
    self.assertEqual('test', conf.GetDefaultBundle()['id'])

  def testGetDefaultBundleNotFound(self):
    conf = config.UmpireConfig(EMPTY_SERVICES_CONFIG)

    # A default bundle ID derived from rulesets doesn't exist in bundles
    # section.
    conf['rulesets'].insert(0, {'bundle_id': 'new_bundle', 'active': True})
    self.assertIsNone(conf.GetDefaultBundle())

    # no active ruleset.
    conf['rulesets'][1]['active'] = False
    self.assertIsNone(conf.GetDefaultBundle())

    # no ruleset.
    del conf['rulesets'][:]
    self.assertIsNone(conf.GetDefaultBundle())

  def testGetBundle(self):
    conf = config.UmpireConfig(EMPTY_SERVICES_CONFIG)
    new_bundle = copy.deepcopy(conf['bundles'][0])
    new_bundle['id'] = 'new_bundle'
    new_bundle['note'] = 'new bundle for test'
    new_bundle['payloads'] = 'new payloads'
    conf['bundles'].append(new_bundle)
    conf.BuildBundleMap()

    bundle = conf.GetBundle('test')
    self.assertEqual('test', bundle['id'])
    self.assertEqual('bundle for test', bundle['note'])
    self.assertEqual('payload.99914b932bd37a50b983c5e7c90ae93b.json',
                     bundle['payloads'])

    bundle = conf.GetBundle('new_bundle')
    self.assertEqual('new_bundle', bundle['id'])
    self.assertEqual('new bundle for test', bundle['note'])
    self.assertEqual('new payloads', bundle['payloads'])

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


class ValidateResourcesTest(unittest.TestCase):

  def setUp(self):
    self.env = umpire_env.UmpireEnvForTest()
    self.conf = config.UmpireConfig(RESOURCE_CHECK_CONFIG, validate=False)
    self.env.AddConfigFromBlob('{}', resource.ConfigTypeNames.payload_config)
    self.env.AddConfigFromBlob('{"hwid":{"file":"hwid.404.gz"}}',
                               resource.ConfigTypeNames.payload_config)

  def tearDown(self):
    self.env.Close()

  def testNormal(self):
    config.ValidateResources(self.conf, self.env)

  def testFileNotFound(self):
    # Resources in the second ruleset's bundle are not presented.
    self.conf['rulesets'][1]['active'] = True
    self.assertRaisesRegexp(common.UmpireError, 'NOT FOUND.+hwid.404.gz',
                            config.ValidateResources, self.conf, self.env)


class ShowDiffTest(unittest.TestCase):

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
         'Deleted rulesets:',
         '  bundle_id: original_bundle',
         '  note: ruleset 1',
         '  active: true'],
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
         '  active: true'],
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
         '  active: true'],
        config.ShowDiff(original, new))


if __name__ == '__main__':
  unittest.main()