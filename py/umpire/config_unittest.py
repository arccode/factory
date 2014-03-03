#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import os
import re
import sys
import unittest
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import config
from cros.factory.utils import file_utils

TESTDATA_DIR = os.path.join(os.path.dirname(sys.modules[__name__].__file__),
                            'testdata')
MINIMAL_CONFIG = os.path.join(TESTDATA_DIR, 'minimal_umpire.yaml')
EMPTY_SERVICES_CONFIG = os.path.join(TESTDATA_DIR,
                                     'minimal_empty_services_umpire.yaml')
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
    self.assertEqual('test', conf.GetDefaultBundle())

    conf['rulesets'].append({'bundle_id': 'new_bundle',
                             'active': True})
    self.assertEqual('new_bundle', conf.GetDefaultBundle())

    # Last ruleset is inactive, use the upper one.
    conf['rulesets'][1]['active'] = False
    self.assertEqual('test', conf.GetDefaultBundle())

  def testGetDefaultBundleNotFound(self):
    conf = config.UmpireConfig(EMPTY_SERVICES_CONFIG)

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

    bundle = conf.GetBundle('test')
    self.assertEqual('test', bundle['id'])
    self.assertEqual('bundle for test', bundle['note'])
    self.assertEqual('complete.gz##00000000',
                     bundle['resources']['complete_script'])

    bundle = conf.GetBundle('new_bundle')
    self.assertEqual('new_bundle', bundle['id'])
    self.assertEqual('new bundle for test', bundle['note'])
    self.assertEqual('complete.gz##00000001',
                     bundle['resources']['complete_script'])

    self.assertIsNone(conf.GetBundle('nonexist_bundle'))


if __name__ == '__main__':
  unittest.main()
