#!/usr/bin/env python2
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import subprocess
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire.server import config as umpire_config
from cros.factory.umpire.server.service import http
from cros.factory.umpire.server import umpire_env


class HTTPServiceTest(unittest.TestCase):

  def setUp(self):
    self.env = umpire_env.UmpireEnvForTest()

  def tearDown(self):
    self.env.Close()

  def testGenerateLightyConfig(self):
    umpire_config_dict = {
        'services': {'http': {
            'reverse_proxies': [
                {'remoteip': '192.168.51.0/24',
                 'proxy_addr': '192.168.51.1:8080'},
                {'remoteip': '192.168.52.0/24',
                 'proxy_addr': '192.168.52.1:8080'}]}},
        'bundles': [{
            'id': 'default',
            'note': '',
            'payloads': 'payload.99914b932bd37a50b983c5e7c90ae93b.json'}],
        'active_bundle_id': 'default'}
    self.env.config = umpire_config.UmpireConfig(umpire_config_dict)
    config_path = http.HTTPService.GenerateNginxConfig(
        umpire_config_dict, self.env)

    self.assertRegexpMatches(
        config_path,
        os.path.join(self.env.config_dir, 'nginx_#[0-9a-f]{32}#.conf'))

    if subprocess.call(['sudo', 'which', 'nginx']):
      raise RuntimeError(
          'Nginx is not installed. '
          'Install nginx (`update_chroot` or `sudo emerge nginx`) then '
          'run this unittest again.')
    else:
      subprocess.check_call(['sudo', 'nginx', '-t', '-c', config_path])


if __name__ == '__main__':
  unittest.main()
