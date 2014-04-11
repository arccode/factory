#!/usr/bin/env python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Unit tests for archiver"""

import archiver
import logging
import os
import random
import shutil
import string  # pylint: disable=W0402
import time
import unittest
import yaml

import archiver_config

import factory_common  # pylint: disable=W0611

from archiver_cli import main
from archiver_exception import ArchiverFieldError
from archiver_config import GenerateConfig, LockSource, WriteAndTruncateFd
from multiprocessing import Process
from cros.factory.test import utils

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
    # Create empty directory
    utils.TryMakeDirs(os.path.join(TEST_DATA_PATH, 'archives'))
    utils.TryMakeDirs(os.path.join(TEST_DATA_PATH, 'raw/report'))
    utils.TryMakeDirs(os.path.join(TEST_DATA_PATH, 'raw/eventlog'))
    utils.TryMakeDirs(os.path.join(TEST_DATA_PATH, 'raw/regcode'))
    os.chdir(TEST_DATA_PATH)

  def tearDown(self):
    os.chdir(self.pwd)
    try:
      shutil.rmtree(os.path.join(TEST_DATA_PATH, 'archives'))
      shutil.rmtree(os.path.join(TEST_DATA_PATH, 'raw/report'))
      shutil.rmtree(os.path.join(TEST_DATA_PATH, 'raw/eventlog'))
      shutil.rmtree(os.path.join(TEST_DATA_PATH, 'raw/regcode'))
    except: # pylint: disable=W0702
      pass

  def testYAMLConfigNonExist(self):
    argv = ['dry-run', 'nonexist.yaml']
    self.assertRaises(IOError, main, argv)

  def testIncorrectYAML(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'syntax_incorrect.yaml')]
    self.assertRaises(yaml.YAMLError, main, argv)

  def testWrongYAMLFromat(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'wrong_format.yaml')]
    self.assertRaises(ArchiverFieldError, main, argv)

  def testMissingDataTypes(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'no_data_types.yaml')]
    self.assertRaises(ArchiverFieldError, main, argv)

  def testSetDefaultValue(self):
    yaml_path = os.path.join(TEST_DATA_PATH, 'default_value.yaml')
    with open(yaml_path) as f:
      logging.debug('Validating fields in %r', yaml_path)
      archive_configs = GenerateConfig(yaml.load(f.read()))
    # Verify the if default values are assigned.
    self.assertEqual('.tar.xz', archive_configs[0].compress_format)
    self.assertEqual(86400, archive_configs[0].duration)  # Secs for a day

  def testUnsupportedDataType(self):
    argv = ['dry-run',
            os.path.join(TEST_DATA_PATH, 'unsupported_data_type.yaml')]
    self.assertRaises(ArchiverFieldError, main, argv)

  def testCheckSourceDir(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'invalid_source_dir.yaml')]
    self.assertRaises(ArchiverFieldError, main, argv)

  def testCheckSourceFile(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'invalid_source_file.yaml')]
    self.assertRaises(ArchiverFieldError, main, argv)

  def testCheckArchivedDir(self):
    argv = ['dry-run',
            os.path.join(TEST_DATA_PATH, 'invalid_archived_dir.yaml')]
    self.assertRaises(ArchiverFieldError, main, argv)

  def testCheckRecycleDir(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'invalid_recycle_dir.yaml')]
    self.assertRaises(ArchiverFieldError, main, argv)

  def testCheckProject(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'invalid_project.yaml')]
    self.assertRaises(ArchiverFieldError, main, argv)

  def testSetDuration(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'invalid_duration.yaml')]
    self.assertRaises(ArchiverFieldError, main, argv)

  def testSetDurationInternally(self):
    config = archiver_config.ArchiverConfig('unittest')
    # We should pass an integer instead.
    self.assertRaises(ArchiverFieldError, config.SetDuration, "86400")

  def testSetCompressFormat(self):
    argv = ['dry-run',
            os.path.join(TEST_DATA_PATH, 'invalid_compress_format.yaml')]
    self.assertRaises(ArchiverFieldError, main, argv)

  def testCorrectConfig(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'template.yaml')]
    main(argv)

  def testMissingSource(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'missing_source.yaml')]
    self.assertRaisesRegexp(
        ArchiverFieldError, 'One of source_dir or source_file must be assigned',
        main, argv)

  def testMultipleSources(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'multiple_sources.yaml')]
    self.assertRaisesRegexp(
        ArchiverFieldError,
        'Should only One of source_dir or source_file be assigned',
        main, argv)

  def testMissingProject(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'missing_project.yaml')]
    self.assertRaisesRegexp(
        ArchiverFieldError, 'project must be assigned', main, argv)

  def testMissingArchivedDir(self):
    argv = ['dry-run',
            os.path.join(TEST_DATA_PATH, 'missing_archived_dir.yaml')]
    self.assertRaisesRegexp(
        ArchiverFieldError, 'archived_dir must be assigned',
        main, argv)

  def testLockSource(self):
    with open(os.path.join(TEST_DATA_PATH, 'template.yaml')) as f:
      content = f.read()
    configs = GenerateConfig(yaml.load(content))

    def _Delayed():
      LockSource(configs[0])
      time.sleep(10)

    # Lock the first config in another process
    p = Process(target=_Delayed)
    p.start()
    time.sleep(0.5)  # Give some time for process to start up
    self.assertRaisesRegexp(
        ArchiverFieldError, 'already monitored by another archiver',
        LockSource, configs[0])

    # Test if the lock released while process terminated
    p.terminate()
    time.sleep(0.5)  # Give some time for process to terminate
    lock_path = LockSource(configs[0])
    # Delete the temporary lock file.
    os.unlink(lock_path)

  def testListEligibleFiles(self):
    with open(os.path.join(TEST_DATA_PATH, 'template_eventlog.yaml')) as f:
      content = f.read()
    configs = GenerateConfig(yaml.load(content))
    expected_list = []
    # Generate inputs for testing, different dates also test the recursivity
    # implicitly.

    EVENT_LOG_PATH = os.path.join(TEST_DATA_PATH, 'raw/eventlog/')
    # Test if appended bytes can be detected.
    #   raw/eventlog/20140419/some_bytes_appeneded
    #   raw/eventlog/20140419/.archiver/some_bytes_appeneded.metadata
    utils.TryMakeDirs(
        os.path.join(EVENT_LOG_PATH, '20140419/.archiver'))
    filename = os.path.join(EVENT_LOG_PATH, '20140419/some_bytes_appeneded')
    with open(filename, 'w') as fd:
      fd.write(''.join(random.sample(string.letters, 20)))
    with open(archiver.GetMetadataPath(filename), 'w') as fd:
      WriteAndTruncateFd(
          fd, archiver.GenerateArchiverMetadata(completed_bytes=10))
    expected_list.append((10, 20, filename))

    # Test if taken out from the returned list.
    #   raw/eventlog/20140419/no_bytes_appended
    #   raw/eventlog/20140419/.archiver/no_bytes_appeneded.metadata
    filename = os.path.join(EVENT_LOG_PATH, '20140419/no_bytes_appended')
    with open(filename, 'w') as fd:
      fd.write(''.join(random.sample(string.letters, 20)))
    with open(archiver.GetMetadataPath(filename), 'w') as fd:
      WriteAndTruncateFd(
          fd, archiver.GenerateArchiverMetadata(completed_bytes=20))


    utils.TryMakeDirs(
        os.path.join(EVENT_LOG_PATH, '20140420/.archiver'))
    # Test if metadata re-generated.
    #   1) incorrect YAML:
    #   raw/eventlog/20140420/corrupted_metadata_1
    #   raw/eventlog/20140420/.archiver/corrupted_metadata_1.metadata
    filename = os.path.join(EVENT_LOG_PATH, '20140420/corrupted_metadata_1')
    with open(filename, 'w') as fd:
      fd.write(''.join(random.sample(string.letters, 20)))
    with open(archiver.GetMetadataPath(filename), 'w') as fd:
      WriteAndTruncateFd(fd, ' - where_is_my_bracket: ][')
    expected_list.append((0, 20, filename))

    #   2) valid YAML but incorrect format:
    #   raw/eventlog/20140420/corrupted_metadata_2
    #   raw/eventlog/20140420/.archiver/corrupted_metadata_2.metadata
    filename = os.path.join(EVENT_LOG_PATH, '20140420/corrupted_metadata_2')
    with open(filename, 'w') as fd:
      fd.write(''.join(random.sample(string.letters, 20)))
    with open(archiver.GetMetadataPath(filename), 'w') as fd:
      WriteAndTruncateFd(fd, '- a\n- b\n- c\n')
    expected_list.append((0, 20, filename))

    #   3) valid metadata, but unreasonable completed_bytes:
    #   raw/eventlog/20140420/corrupted_metadata_3
    #   raw/eventlog/20140420/.archiver/corrupted_metadata_3.metadata
    filename = os.path.join(EVENT_LOG_PATH, '20140420/corrupted_metadata_3')
    with open(filename, 'w') as fd:
      fd.write(''.join(random.sample(string.letters, 20)))
    with open(archiver.GetMetadataPath(filename), 'w') as fd:
      WriteAndTruncateFd(
          fd, archiver.GenerateArchiverMetadata(completed_bytes=40))
    expected_list.append((0, 20, filename))


    utils.TryMakeDirs(
        os.path.join(EVENT_LOG_PATH, '20140421'))
    # Test if metadata created automatically.
    #   raw/eventlog/20140421/new_created_file
    filename = os.path.join(EVENT_LOG_PATH, '20140421/new_created_file')
    with open(filename, 'w') as fd:
      fd.write(''.join(random.sample(string.letters, 20)))
    expected_list.append((0, 20, filename))

    # Test if those files are skipped.
    #   raw/eventlog/20140421/creating.inprogress
    #   raw/eventlog/20140421/creating.part
    filename = os.path.join(EVENT_LOG_PATH, '20140421/creating.inprogress')
    with open(filename, 'w') as fd:
      fd.write(''.join(random.sample(string.letters, 20)))
    filename = os.path.join(EVENT_LOG_PATH, '20140421/creating.part')
    with open(filename, 'w') as fd:
      fd.write(''.join(random.sample(string.letters, 20)))

    ret_list = archiver.ListEligibleFiles(configs[0].source_dir)
    self.assertItemsEqual(expected_list, ret_list)


if __name__ == '__main__':
  unittest.main()
