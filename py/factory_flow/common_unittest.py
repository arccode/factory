#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.factory_flow import common
from cros.factory.utils import file_utils


TESTDATA_DIR = os.path.join(os.path.dirname(__file__), 'testdata')


class LoadBundleManifestTest(unittest.TestCase):

  def testNormal(self):
    manifest_path = os.path.join(TESTDATA_DIR, 'sample_MANIFEST.yaml')
    manifest = common.LoadBundleManifest(manifest_path)
    self.assertEqual('daisy_spring', manifest['board'])

  def testIgnoreGlob(self):
    manifest_path = os.path.join(TESTDATA_DIR, 'sample_MANIFEST.yaml')
    manifest = common.LoadBundleManifest(manifest_path, ignore_glob=True)
    self.assertEqual('daisy_spring', manifest['board'])

  def testManifestNotFound(self):
    self.assertRaises(IOError, common.LoadBundleManifest, '/path/not/exists')

  def testInvalidManifest(self):
    with file_utils.UnopenedTemporaryFile() as f:
      file_utils.WriteFile(f, 'key: %scalar cannot start with %')
      self.assertRaises(common.FactoryFlowError, common.LoadBundleManifest, f)


if __name__ == '__main__':
  unittest.main()
