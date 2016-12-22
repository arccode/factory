#!/usr/bin/python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import subprocess
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import config
from cros.factory.umpire.service import overlord
from cros.factory.umpire import umpire_env
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils


class OverlordServiceTest(unittest.TestCase):
  # since we are not sure if the user has emerge chromeos-factory-overlord
  # or not, we use the overlordd in factory/go/bin instead
  OVERLORDD_BIN = '/mnt/host/source/src/platform/factory/go/bin/overlordd'

  def setUp(self):
    # override default path in overlord module
    overlord.OVERLORDD_BIN = self.OVERLORDD_BIN

    self.env = umpire_env.UmpireEnv()
    self.temp_dir = tempfile.mkdtemp()
    self.env.base_dir = self.temp_dir
    os.makedirs(self.env.config_dir)

    # build overlord
    overlordd_dir = os.path.dirname(self.OVERLORDD_BIN)
    source_dir = os.path.join(overlordd_dir, '..', 'src', 'overlord')
    subprocess.call('make -C %s' % source_dir, shell=True)

  def tearDown(self):
    if os.path.isdir(self.temp_dir):
      shutil.rmtree(self.temp_dir)

  def testLaunchOverlord(self):
    umpire_config = {
        'services': {'overlord': {'noauth': True}},
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

    svc = overlord.OverlordService()
    self.env.config = config.UmpireConfig(umpire_config)
    procs = svc.CreateProcesses(umpire_config, self.env)

    # set random port for overlord to bind
    procs[0].config.env = {
        'OVERLORD_PORT': str(net_utils.GetUnusedPort()),
        'OVERLORD_LD_PORT': str(net_utils.GetUnusedPort()),
        'OVERLORD_HTTP_PORT': str(net_utils.GetUnusedPort())
    }

    with self.assertRaises(subprocess.CalledProcessError):
      process_utils.CheckOutput(['pgrep', '-f', overlord.OVERLORDD_BIN])

    svc.Start(procs)
    try:
      def CheckOverlord():
        try:
          process_utils.CheckOutput(['pgrep', '-f', overlord.OVERLORDD_BIN])
          return True
        except subprocess.CalledProcessError:
          return False
      sync_utils.WaitFor(CheckOverlord, 5)
    except:  # pylint: disable=W0702
      self.fail('overlord process not started')
    finally:
      svc.Stop()


if __name__ == '__main__':
  unittest.main()
