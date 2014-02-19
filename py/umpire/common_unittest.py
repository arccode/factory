#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import sys
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import common
from cros.factory.utils import file_utils


TESTDATA_DIR = os.path.join(os.path.dirname(sys.modules[__name__].__file__),
                            'testdata')

class TestGetHashFromResourceName(unittest.TestCase):
  def testNormal(self):
    self.assertEqual(
        '12345678',
        common.GetHashFromResourceName('/foo/bar/resources/buz##12345678'))

  def testNoMatch(self):
    self.assertIsNone(common.GetHashFromResourceName('/foo/bar/resources/buz'))
    self.assertIsNone(
        common.GetHashFromResourceName('/foo/bar/resources/buz#12345678'))


class TestVerifyResource(unittest.TestCase):
  def testNormal(self):
    with file_utils.TempDirectory() as temp_dir:
      test_file = os.path.join(temp_dir, 'test')
      file_utils.WriteFile(test_file, 'test')

      md5sum = file_utils.Md5sumInHex(test_file)
      res_file = '%s##%s' % (test_file, md5sum[:common.RESOURCE_HASH_DIGITS])
      os.rename(test_file, res_file)

      self.assertTrue(common.VerifyResource(res_file))

  def testFileMissing(self):
    self.assertFalse(common.VerifyResource('/foo/bar/buz'))

  def testIllFormedName(self):
    with file_utils.TempDirectory() as temp_dir:
      test_file = os.path.join(temp_dir, 'test')
      file_utils.WriteFile(test_file, 'test')

      self.assertFalse(common.VerifyResource(test_file))


class TestLoadBundleManifest(unittest.TestCase):
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
      self.assertRaises(common.UmpireError, common.LoadBundleManifest, f)

class TestParseResourceName(unittest.TestCase):
  def testNormal(self):
    self.assertTupleEqual(
        ('/foo/bar/resources/buz', '', '12345678'),
        common.ParseResourceName('/foo/bar/resources/buz##12345678'))

  def testNoMatch(self):
    self.assertIsNone(common.ParseResourceName('/foo/bar/resources/buz'))
    self.assertIsNone(common.ParseResourceName(
        '/foo/bar/resources/buz#12345678'))


if __name__ == '__main__':
  unittest.main()
