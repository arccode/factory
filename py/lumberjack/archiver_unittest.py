#!/usr/bin/env python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Unit tests for archiver"""

import archiver
import logging
import os
import time
import unittest
import yaml

from archiver import ArchiverFieldError
from multiprocessing import Process

TEST_DATA_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), 'testdata/archiver'))


class ArchiverUnittest(unittest.TestCase):
  """Unit tests for archiver"""
  pwd = None
  def setUp(self):
    logging.basicConfig(
        format=('[%(levelname)s] archiver:%(lineno)d %(asctime)s %(message)s'),
        level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')
    self.pwd = os.getcwd()
    os.chdir(TEST_DATA_PATH)

  def tearDown(self):
    os.chdir(self.pwd)

  def testYAMLConfigNonExist(self):
    argv = ['dry-run', 'nonexist.yaml']
    self.assertRaises(IOError, archiver.main, argv)

  def testIncorrectYAML(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'syntax_incorrect.yaml')]
    self.assertRaises(yaml.YAMLError, archiver.main, argv)

  def testWrongYAMLFromat(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'wrong_format.yaml')]
    self.assertRaises(ArchiverFieldError, archiver.main, argv)

  def testMissingDataTypes(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'no_data_types.yaml')]
    self.assertRaises(ArchiverFieldError, archiver.main, argv)

  def testSetDefaultValue(self):
    yaml_path = os.path.join(TEST_DATA_PATH, 'default_value.yaml')
    with open(yaml_path) as f:
      logging.debug('Validating fields in %r', yaml_path)
      archive_configs = archiver.GenerateConfig(yaml.load(f.read()))
    # Verify the if default values are assigned.
    self.assertEqual('.tar.xz', archive_configs[0].compress_format)
    self.assertEqual(86400, archive_configs[0].duration)  # Secs for a day

  def testUnsupportedDataType(self):
    argv = ['dry-run',
            os.path.join(TEST_DATA_PATH, 'unsupported_data_type.yaml')]
    self.assertRaises(ArchiverFieldError, archiver.main, argv)

  def testCheckSourceDir(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'invalid_source_dir.yaml')]
    self.assertRaises(ArchiverFieldError, archiver.main, argv)

  def testCheckSourceFile(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'invalid_source_file.yaml')]
    self.assertRaises(ArchiverFieldError, archiver.main, argv)

  def testCheckArchivedDir(self):
    argv = ['dry-run',
            os.path.join(TEST_DATA_PATH, 'invalid_archived_dir.yaml')]
    self.assertRaises(ArchiverFieldError, archiver.main, argv)

  def testCheckRecycleDir(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'invalid_recycle_dir.yaml')]
    self.assertRaises(ArchiverFieldError, archiver.main, argv)

  def testCheckProject(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'invalid_project.yaml')]
    self.assertRaises(ArchiverFieldError, archiver.main, argv)

  def testSetDuration(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'invalid_duration.yaml')]
    self.assertRaises(ArchiverFieldError, archiver.main, argv)

  def testSetDurationInternally(self):
    config = archiver.ArchiverConfig('unittest')
    # We should pass an integer instead.
    self.assertRaises(ArchiverFieldError, config.SetDuration, "86400")

  def testSetCompressFormat(self):
    argv = ['dry-run',
            os.path.join(TEST_DATA_PATH, 'invalid_compress_format.yaml')]
    self.assertRaises(ArchiverFieldError, archiver.main, argv)

  def testCorrectConfig(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'template.yaml')]
    archiver.main(argv)

  def testMissingSource(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'missing_source.yaml')]
    self.assertRaisesRegexp(
        ArchiverFieldError, 'One of source_dir or source_file must be assigned',
        archiver.main, argv)

  def testMultipleSources(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'multiple_sources.yaml')]
    self.assertRaisesRegexp(
        ArchiverFieldError,
        'Should only One of source_dir or source_file be assigned',
        archiver.main, argv)

  def testMissingProject(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'missing_project.yaml')]
    self.assertRaisesRegexp(
        ArchiverFieldError, 'project must be assigned', archiver.main, argv)

  def testMissingArchivedDir(self):
    argv = ['dry-run',
            os.path.join(TEST_DATA_PATH, 'missing_archived_dir.yaml')]
    self.assertRaisesRegexp(
        ArchiverFieldError, 'archived_dir must be assigned',
        archiver.main, argv)

  def testLockSource(self):
    with open(os.path.join(TEST_DATA_PATH, 'template.yaml')) as f:
      content = f.read()
    configs = archiver.GenerateConfig(yaml.load(content))

    def _Delayed():
      archiver.LockSource(configs[0])
      time.sleep(10)

    # Lock the first config in another process
    p = Process(target=_Delayed)
    p.start()
    time.sleep(0.5)  # Give some time for process to start up
    self.assertRaisesRegexp(
        ArchiverFieldError, 'already monitored by another archiver',
        archiver.LockSource, configs[0])

    # Test if the lock released while process terminated
    p.terminate()
    time.sleep(0.5)  # Give some time for process to terminate
    lock_path = archiver.LockSource(configs[0])
    # Delete the temporary lock file.
    os.unlink(lock_path)


if __name__ == '__main__':
  unittest.main()
