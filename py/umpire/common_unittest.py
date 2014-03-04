#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import sys
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.common import (LoadBundleManifest, UmpireError)
from cros.factory.utils import file_utils


TESTDATA_DIR = os.path.join(os.path.dirname(sys.modules[__name__].__file__),
                            'testdata')


class TestLoadBundleManifestIgnoreGlob(unittest.TestCase):
  def testNormal(self):
    manifest_path = os.path.join(TESTDATA_DIR, 'sample_MANIFEST.yaml')
    manifest = LoadBundleManifest(manifest_path)
    self.assertEqual('daisy_spring', manifest['board'])

  def testIgnoreGlob(self):
    manifest_path = os.path.join(TESTDATA_DIR, 'sample_MANIFEST.yaml')
    manifest = LoadBundleManifest(manifest_path, ignore_glob=True)
    self.assertEqual('daisy_spring', manifest['board'])

  def testManifestNotFound(self):
    self.assertRaises(IOError, LoadBundleManifest, '/path/not/exists')

  def testInvalidManifest(self):
    with file_utils.UnopenedTemporaryFile() as f:
      file_utils.WriteFile(f, 'key: %scalar cannot start with %')
      self.assertRaises(UmpireError, LoadBundleManifest, f)


if __name__ == '__main__':
  unittest.main()
