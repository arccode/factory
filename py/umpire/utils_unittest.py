#!/usr/bin/env python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=E1101


import os
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import common
from cros.factory.umpire import umpire_env
from cros.factory.umpire import utils
from cros.factory.utils import file_utils


TEST_DIR = os.path.dirname(__file__)
TESTDATA_DIR = os.path.join(TEST_DIR, 'testdata')
TOOLKIT_PATH = os.path.join(TESTDATA_DIR, 'install_factory_toolkit.run')
# MD5 and unpacked content of TOOLKIT
TOOLKIT_MD5 = '7509337e'
UMPIRE_RELATIVE_PATH = os.path.join('usr', 'local', 'factory', 'bin', 'umpire')


class RegistryTest(unittest.TestCase):

  def testRegistry(self):
    reg = utils.Registry()
    reg['foo'] = 'value_foo'
    reg['bar'] = 'value_foo'

    test_reg = utils.Registry()
    self.assertEqual(test_reg.foo, 'value_foo')
    self.assertNotEqual(test_reg.bar, 'value_bar')


class UnpackFactoryToolkitTest(unittest.TestCase):

  def setUp(self):
    self.env = umpire_env.UmpireEnvForTest()

    self.toolkit_resource = self.env.AddResource(TOOLKIT_PATH)

  def tearDown(self):
    self.env.Close()

  def testUnpackToolkit(self):
    expected_toolkit_dir = os.path.join(self.env.device_toolkits_dir,
                                        TOOLKIT_MD5)
    self.assertEqual(
        expected_toolkit_dir,
        utils.UnpackFactoryToolkit(self.env, self.toolkit_resource))
    umpire_path = os.path.join(expected_toolkit_dir, UMPIRE_RELATIVE_PATH)
    self.assertTrue(os.path.exists(umpire_path))

    # Exam MD5SUM file.
    expected_md5sum_path = os.path.join(expected_toolkit_dir, 'usr', 'local',
                                        'factory', 'MD5SUM')
    self.assertTrue(os.path.exists(expected_md5sum_path))
    self.assertEqual(TOOLKIT_MD5, file_utils.ReadFile(expected_md5sum_path))

  def testNoUnpackDestExist(self):
    expected_toolkit_dir = os.path.join(self.env.device_toolkits_dir,
                                        TOOLKIT_MD5)
    # Create target directory.
    os.makedirs(expected_toolkit_dir)
    self.assertEqual(expected_toolkit_dir,
                     utils.UnpackFactoryToolkit(self.env,
                                                self.toolkit_resource))

    # Verify that the toolkit isn't unpacked to it.
    self.assertFalse(os.path.exists(os.path.join(expected_toolkit_dir,
                                                 UMPIRE_RELATIVE_PATH)))

  def testNoUnpackInvalidToolkitResource(self):
    self.assertIsNone(utils.UnpackFactoryToolkit(self.env, None))


class GetHashFromResourceNameTest(unittest.TestCase):

  def testNormal(self):
    self.assertEqual(
        '12345678',
        utils.GetHashFromResourceName('/foo/bar/resources/buz##12345678'))

  def testNoMatch(self):
    self.assertIsNone(utils.GetHashFromResourceName('/foo/bar/resources/buz'))
    self.assertIsNone(
        utils.GetHashFromResourceName('/foo/bar/resources/buz#12345678'))


class GetVersionFromResourceNameTest(unittest.TestCase):

  def testNormal(self):
    self.assertEqual(
        'ver1.1.1',
        utils.GetVersionFromResourceName(
            '/foo/bar/resources/buz#ver1.1.1#12345678'))
    self.assertEqual(
        '',
        utils.GetVersionFromResourceName(
            '/foo/bar/resources/buz##12345678'))

  def testNoMatch(self):
    self.assertIsNone(
        utils.GetVersionFromResourceName('/foo/bar/resources/buz'))
    self.assertIsNone(
        utils.GetVersionFromResourceName('/foo/bar/resources/buz#12345678'))


class VerifyResourceTest(unittest.TestCase):

  def testNormal(self):
    with file_utils.TempDirectory() as temp_dir:
      test_file = os.path.join(temp_dir, 'test')
      file_utils.WriteFile(test_file, 'test')

      md5sum = file_utils.Md5sumInHex(test_file)
      res_file = '%s##%s' % (test_file, md5sum[:common.RESOURCE_HASH_DIGITS])
      os.rename(test_file, res_file)

      self.assertTrue(utils.VerifyResource(res_file))

  def testFileMissing(self):
    self.assertFalse(utils.VerifyResource('/foo/bar/buz'))

  def testIllFormedName(self):
    with file_utils.TempDirectory() as temp_dir:
      test_file = os.path.join(temp_dir, 'test')
      file_utils.WriteFile(test_file, 'test')

      self.assertFalse(utils.VerifyResource(test_file))


class LoadBundleManifestTest(unittest.TestCase):

  def testNormal(self):
    manifest_path = os.path.join(TESTDATA_DIR, 'sample_MANIFEST.yaml')
    manifest = utils.LoadBundleManifest(manifest_path)
    self.assertEqual('daisy_spring', manifest['board'])

  def testIgnoreGlob(self):
    manifest_path = os.path.join(TESTDATA_DIR, 'sample_MANIFEST.yaml')
    manifest = utils.LoadBundleManifest(manifest_path, ignore_glob=True)
    self.assertEqual('daisy_spring', manifest['board'])

  def testManifestNotFound(self):
    self.assertRaises(IOError, utils.LoadBundleManifest, '/path/not/exists')

  def testInvalidManifest(self):
    with file_utils.UnopenedTemporaryFile() as f:
      file_utils.WriteFile(f, 'key: %scalar cannot start with %')
      self.assertRaises(common.UmpireError, utils.LoadBundleManifest, f)


class ParseResourceNameTest(unittest.TestCase):

  def testNormal(self):
    self.assertTupleEqual(
        ('/foo/bar/resources/buz', '', '12345678'),
        utils.ParseResourceName('/foo/bar/resources/buz##12345678'))

    self.assertTupleEqual(
        ('/foo/bar/resources/buz', 'ver1.1.1', '12345678'),
        utils.ParseResourceName('/foo/bar/resources/buz#ver1.1.1#12345678'))

  def testNoMatch(self):
    self.assertIsNone(utils.ParseResourceName('/foo/bar/resources/buz'))
    self.assertIsNone(utils.ParseResourceName(
        '/foo/bar/resources/buz#12345678'))


if __name__ == '__main__':
  unittest.main()
