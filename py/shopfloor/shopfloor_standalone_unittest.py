#!/usr/bin/env python

# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Makes sure that shopfloor server can run in a standalone
environment (with only factory.par)."""

import logging
import os
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.env import paths
from cros.factory.utils.process_utils import Spawn


class ShopFloorStandaloneTest(unittest.TestCase):

  def setUp(self):
    self.process = None
    self.tmp = tempfile.mkdtemp(prefix='shopfloor_standalone_unittest.')
    self.tmp_build_dir = tempfile.mkdtemp(
        prefix='shopfloor_standalone_unittest_build_dir.')

  def tearDown(self):
    if self.process and self.process.poll() is None:
      try:
        self.process.terminate()
      except:
        pass
    shutil.rmtree(self.tmp)
    shutil.rmtree(self.tmp_build_dir)

  def runTest(self):
    script_dir = os.path.dirname(os.path.realpath(__file__))
    Spawn(['make', '-s', '-C', paths.FACTORY_PATH,
           'par', 'PAR_DEST_DIR=%s' % self.tmp,
           'PAR_BUILD_DIR=%s' % self.tmp_build_dir],
          log=True, check_call=True)

    shopfloor_server_path = os.path.join(self.tmp, 'shopfloor_server')
    os.symlink(os.path.realpath(os.path.join(self.tmp, 'factory.par')),
               shopfloor_server_path)

    os.environ['SHOPFLOOR_SERVER_CMD'] = shopfloor_server_path
    # Disable all site directories to simulate a plain-vanilla Python.
    os.environ['CROS_SHOPFLOOR_PYTHON_OPTS'] = '-sS'

    shopfloor_unittest = os.path.join(script_dir, 'shopfloor_unittest.py')
    self.process = Spawn([shopfloor_unittest], check_call=True, log=True)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
