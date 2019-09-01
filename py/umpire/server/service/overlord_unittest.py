#!/usr/bin/env python2
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import subprocess
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire.server import config
from cros.factory.umpire.server.service import overlord
from cros.factory.umpire.server import umpire_env
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils


class OverlordServiceTest(unittest.TestCase):
  def setUp(self):
    self.temp_bin_dir = tempfile.mkdtemp()
    # override default path in overlord module
    overlord.OVERLORDD_BIN = self.temp_bin_dir + '/overlordd'

    self.env = umpire_env.UmpireEnv()
    self.temp_dir = tempfile.mkdtemp()
    self.env.base_dir = self.temp_dir
    os.makedirs(self.env.config_dir)

    # build overlord
    source_dir = '/mnt/host/source/src/platform/factory/go/src/overlord'
    subprocess.call('make -C %s BINDIR=%s' % (source_dir, self.temp_bin_dir),
                    shell=True)

  def tearDown(self):
    if os.path.isdir(self.temp_dir):
      shutil.rmtree(self.temp_dir)
    if os.path.isdir(self.temp_bin_dir):
      shutil.rmtree(self.temp_bin_dir)

  def testLaunchOverlord(self):
    umpire_config = {
        'services': {'overlord': {'noauth': True}},
        'bundles': [{
            'id': 'default',
            'note': '',
            'payloads': 'payload.99914b932bd37a50b983c5e7c90ae93b.json'}],
        'active_bundle_id': 'default'}

    svc = overlord.OverlordService()
    self.env.config = config.UmpireConfig(umpire_config)
    procs = svc.CreateProcesses(umpire_config, self.env)

    # set random port for overlord to bind
    procs[0].config.env = {
        'OVERLORD_PORT': str(net_utils.FindUnusedPort()),
        'OVERLORD_LD_PORT': str(net_utils.FindUnusedPort()),
        'OVERLORD_HTTP_PORT': str(net_utils.FindUnusedPort())
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
    except Exception:
      self.fail('overlord process not started')
    finally:
      svc.Stop()


if __name__ == '__main__':
  unittest.main()
