#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import os
import pprint
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.config import UmpireConfig
from cros.factory.umpire.service import shop_floor
from cros.factory.umpire.umpire_env import UmpireEnv


class MockShopFloorManager(object):
  def Allocate(self, *unused_args, **unused_kwargs):
    return (9876, 'dummy_token')

  def Release(self, port):
    if port != 9876:
      raise ValueError('Release without Allocate')


class TestShopFloorService(unittest.TestCase):
  def setUp(self):
    self.env = UmpireEnv()
    self.temp_dir = tempfile.mkdtemp()
    self.env.base_dir = self.temp_dir
    os.makedirs(self.env.resources_dir)
    self.env.shop_floor_manager = MockShopFloorManager()

  def tearDown(self):
    if os.path.isdir(self.temp_dir):
      shutil.rmtree(self.temp_dir)

  def testGenerateProcesses(self):
    umpire_config = {
        # 4 active rulesets, 3 active.
        'rulesets': [
            {'bundle_id': 'bundle_1', 'note': 'note_1', 'active': True},
            {'bundle_id': 'bundle_2', 'note': 'note_2', 'active': True},
            {'bundle_id': 'bundle_3', 'note': 'note_3', 'active': False},
            {'bundle_id': 'bundle_d', 'note': 'note_d', 'active': True}],
        # 4 bundles.
        'bundles': [
            {'id': 'bundle_1', 'note': 'note_b_1',
             'shop_floor': {'handler': 'handler_1'},
             'resources': {'device_factory_toolkit':
                           'install_factory_toolkit.run#ftk_1#00000001'}},
            {'id': 'bundle_2', 'note': 'note_b_2',
             'shop_floor': {'handler': 'handler_2'},
             'resources': {'device_factory_toolkit':
                           'install_factory_toolkit.run#ftk_2#00000002'}},
            {'id': 'bundle_3', 'note': 'note_b_3',
             'shop_floor': {'handler': 'handler_3'},
             'resources': {'device_factory_toolkit':
                           'install_factory_toolkit.run#ftk_3#00000003'}},
            {'id': 'bundle_d', 'note': 'note_b_d',
             'shop_floor': {'handler': 'handler_d'},
             'resources': {'device_factory_toolkit':
                           'install_factory_toolkit.run#ftk_4#00000004'}}]}
    # Activate configuration.
    self.env.config = UmpireConfig(umpire_config, validate=False)
    os.makedirs(self.env.device_toolkits_dir)
    map(lambda h: os.makedirs(os.path.join(self.env.device_toolkits_dir, h)),
        ['00000001', '00000002', '00000003', '00000004'])
    # Create processes.
    service = shop_floor.ShopFloorService()
    processes = service.CreateProcesses(None, self.env)
    # Check process count.
    num_actives = sum([b['active'] for b in umpire_config['rulesets']])
    logging.debug('process config:\n%s',
                  pprint.pformat(sum([[p.config, p.nonhash_args]
                                      for p in processes], list()),
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
