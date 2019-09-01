#!/usr/bin/env python2
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import json
import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire import common
from cros.factory.umpire.server import config
from cros.factory.umpire.server import resource
from cros.factory.umpire.server import umpire_env
from cros.factory.utils import file_utils

TESTDATA_DIR = os.path.join(os.path.dirname(__file__), 'testdata')
MINIMAL_CONFIG = os.path.join(TESTDATA_DIR, 'minimal_umpire.json')
EMPTY_SERVICES_CONFIG = os.path.join(TESTDATA_DIR,
                                     'minimal_empty_services_umpire.json')
RESOURCE_CHECK_CONFIG = os.path.join(TESTDATA_DIR,
                                     'umpire_resource_check.json')


class UmpireConfigTest(unittest.TestCase):

  def _CheckConfig(self, conf):
    self.assertEqual(1, len(conf['bundles']))
    self.assertEqual('test', conf['active_bundle_id'])

    bundle = conf['bundles'][0]
    self.assertEqual('test', bundle['id'])
    self.assertEqual('bundle for test', bundle['note'])

  def testLoadConfig(self):
    conf = config.UmpireConfig(file_path=EMPTY_SERVICES_CONFIG)
    self._CheckConfig(conf)

  def testLoadConfigNotFound(self):
    self.assertRaises(
        IOError, config.UmpireConfig, file_path='/path/to/no/where')

  def testLoadConfigFromDict(self):
    with open(EMPTY_SERVICES_CONFIG) as f:
      config_dict = json.load(f)
    conf = config.UmpireConfig(config=config_dict)
    self._CheckConfig(conf)

  def testLoadConfigString(self):
    config_str = file_utils.ReadFile(EMPTY_SERVICES_CONFIG)
    conf = config.UmpireConfig(config=config_str)
    self._CheckConfig(conf)

  def testLoadConfigFromConfigDeepCopy(self):
    conf = config.UmpireConfig(file_path=EMPTY_SERVICES_CONFIG)
    original_payloads = conf['bundles'][0]['payloads']

    dup_conf = config.UmpireConfig(conf)
    dup_conf['bundles'][0]['payloads'] = 'new payloads'

    # Make sure that the structure is deep-copied.
    self.assertEqual(original_payloads, conf['bundles'][0]['payloads'])

  def testDumpConfig(self):
    conf = config.UmpireConfig(file_path=MINIMAL_CONFIG)
    new_config = conf.Dump()

    self.assertEqual(conf, json.loads(new_config))

  def testGetActiveBundle(self):
    conf = config.UmpireConfig(file_path=EMPTY_SERVICES_CONFIG)
    self.assertEqual('test', conf.GetActiveBundle()['id'])

    new_bundle = copy.deepcopy(conf['bundles'][0])
    new_bundle['id'] = 'new_bundle'
    conf['bundles'].append(new_bundle)
    conf = config.UmpireConfig(conf)
    self.assertEqual('test', conf.GetActiveBundle()['id'])

    conf['active_bundle_id'] = 'new_bundle'
    self.assertEqual('new_bundle', conf.GetActiveBundle()['id'])

  def testGetActiveBundleNotFound(self):
    conf = config.UmpireConfig(file_path=EMPTY_SERVICES_CONFIG)
    # no active bundle.
    conf['active_bundle_id'] = 'nonexist_bundle'
    self.assertRaises(common.UmpireError, conf.GetActiveBundle)

  def testGetBundle(self):
    conf = config.UmpireConfig(file_path=EMPTY_SERVICES_CONFIG)
    new_bundle = copy.deepcopy(conf['bundles'][0])
    new_bundle['id'] = 'new_bundle'
    new_bundle['note'] = 'new bundle for test'
    new_bundle['payloads'] = 'new payloads'
    conf['bundles'].append(new_bundle)
    conf = config.UmpireConfig(conf)

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


class ValidateResourcesTest(unittest.TestCase):

  def setUp(self):
    self.env = umpire_env.UmpireEnvForTest()
    self.conf = config.UmpireConfig(
        file_path=RESOURCE_CHECK_CONFIG, validate=False)
    self.env.AddConfigFromBlob('{}', resource.ConfigTypeNames.payload_config)
    self.env.AddConfigFromBlob('{"hwid":{"file":"hwid.404.gz"}}',
                               resource.ConfigTypeNames.payload_config)

  def tearDown(self):
    self.env.Close()

  def testNormal(self):
    config.ValidateResources(self.conf, self.env)

  def testFileNotFound(self):
    # Resources in the second bundle are not presented.
    self.conf['active_bundle_id'] = 'test2'
    self.assertRaisesRegexp(common.UmpireError, 'NOT FOUND.+hwid.404.gz',
                            config.ValidateResources, self.conf, self.env)


if __name__ == '__main__':
  unittest.main()
