#!/usr/bin/env python2
#
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire.server import umpire_env
from cros.factory.umpire.server import webapp_resourcemap


TESTDIR = os.path.abspath(os.path.join(os.path.split(__file__)[0], 'testdata'))
TESTCONFIG = os.path.join(TESTDIR, 'minimal_empty_services_umpire.json')


class GetResourceMapTest(unittest.TestCase):

  def setUp(self):
    self.env = umpire_env.UmpireEnvForTest()
    shutil.copy(TESTCONFIG, self.env.active_config_file)
    self.env.LoadConfig()

  def tearDown(self):
    self.env.Close()

  def runTest(self):
    self.assertEqual(
        'id: test\n'
        'note: bundle for test\n'
        '__token__: 00000001\n'
        'shop_floor_handler: /umpire\n'
        'payloads: payload.99914b932bd37a50b983c5e7c90ae93b.json\n',
        webapp_resourcemap.GetResourceMap(self.env))


if __name__ == '__main__':
  unittest.main()
