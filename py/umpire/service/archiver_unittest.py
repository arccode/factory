#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.lumberjack import archiver_cli
from cros.factory.umpire import config
from cros.factory.umpire.service import archiver
from cros.factory.umpire import umpire_env


class ArchiverServiceTest(unittest.TestCase):

  def setUp(self):
    self.env = umpire_env.UmpireEnvForTest()

    # Create fake log directories.
    self.archived_dir = os.path.join(self.env.base_dir, 'archived_dir')
    self.eventlog_dir = os.path.join(self.env.base_dir, 'raw', 'eventlog')
    self.reports_dir = os.path.join(self.env.base_dir, 'raw', 'report')
    self.regcode_dir = os.path.join(self.env.base_dir, 'raw', 'regcode')
    os.makedirs(self.archived_dir)
    os.makedirs(self.eventlog_dir)
    os.makedirs(self.reports_dir)
    os.makedirs(self.regcode_dir)
    # Prepare server toolkit.
    factory_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    for subdir in ['py', 'py_pkg', 'bin']:
      os.symlink(
          os.path.join(factory_dir, subdir),
          os.path.join(self.env.server_toolkit_dir, subdir))

    self.umpire_config = {
        'port': 9001,
        'services': {'archiver': {
            'common': {'archived_dir': self.archived_dir},
            'data_types': {
                'eventlog': {'source_dir': self.eventlog_dir},
                'reports': {'source_dir': self.reports_dir},
                'regcode': {'source_dir': self.regcode_dir},
            }}},
        'bundles': [{
            'id': 'default',
            'note': '',
            'shop_floor': {'handler': ''},
            'resources': {
                'device_factory_toolkit': '',
                'stateful_partition': '',
                'oem_partition': '',
                'rootfs_release': '',
                'rootfs_test': ''}}],
        'rulesets': [{
            'bundle_id': 'default',
            'note': '',
            'active': True}]}

  def tearDown(self):
    self.env.Close()

  def testGenerateConfig(self):
    self.env.config = config.UmpireConfig(self.umpire_config)
    config_path = archiver.ArchiverService.GenerateConfig(
        self.umpire_config, self.env)
    # Dry run with the config_path
    argv = ['dry-run', config_path]
    archiver_cli.main(argv)


if __name__ == '__main__':
  logging.basicConfig(
      format=('[%(levelname)s] archiver_unittest:%(lineno)d'
              '%(asctime)s %(message)s'),
      level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')
  unittest.main()
