#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import logging
import os
import pprint
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import config
from cros.factory.umpire import resource
from cros.factory.umpire.service import shop_floor
from cros.factory.umpire import umpire_env


class MockShopFloorManager(object):

  def Allocate(self, *args, **kwargs):
    del args, kwargs  # Unused.
    return (9876, 'dummy_token')

  def Release(self, port):
    if port != 9876:
      raise ValueError('Release without Allocate')


class ShopFloorServiceTest(unittest.TestCase):

  def setUp(self):
    self.env = umpire_env.UmpireEnvForTest()
    self.env.shop_floor_manager = MockShopFloorManager()

  def tearDown(self):
    self.env.Close()

  def testGenerateProcesses(self):
    os.makedirs(self.env.device_toolkits_dir)
    bundles = []
    for i in xrange(1, 5):  # 4 bundles.
      h = '%032d' % i
      os.makedirs(os.path.join(self.env.device_toolkits_dir, h))
      payloads = {'toolkit': {'file': 'toolkit.%s.gz' % h}}
      bundles.append({
          'id': 'bundle_%d' % i,
          'note': 'note_b_%d' % i,
          'shop_floor': {'handler': 'handler_%d' % i},
          'payloads': os.path.basename(
              self.env.AddConfigFromBlob(
                  json.dumps(payloads),
                  resource.ConfigTypeNames.payload_config))})

    umpire_config = {
        'services': {'shop_floor': {}},
        # 4 active rulesets, 3 active.
        'rulesets': [
            {'bundle_id': 'bundle_1', 'note': 'note_1', 'active': True},
            {'bundle_id': 'bundle_2', 'note': 'note_2', 'active': True},
            {'bundle_id': 'bundle_3', 'note': 'note_3', 'active': False},
            {'bundle_id': 'bundle_4', 'note': 'note_4', 'active': True}],
        'bundles': bundles}
    # Activate configuration.
    self.env.config = config.UmpireConfig(umpire_config, validate=False)
    # Create processes.
    service = shop_floor.ShopFloorService()
    processes = service.CreateProcesses(umpire_config, self.env)
    # Check process count.
    num_actives = sum([b['active'] for b in umpire_config['rulesets']])
    logging.debug('process config:\n%s',
                  pprint.pformat(sum([[p.config, p.nonhash_args]
                                      for p in processes], []),
                                 indent=2))
    self.assertEqual(num_actives, len(processes))


if __name__ == '__main__':
  if os.environ.get('LOG_LEVEL'):
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(levelname)5s %(message)s')
  else:
    logging.disable(logging.CRITICAL)

  unittest.main()
