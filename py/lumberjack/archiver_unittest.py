#!/usr/bin/env python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Unit tests for archiver"""

import logging
import os
import shutil
import tempfile
import time
import unittest
import yaml

import archiver
import archiver_config

from archiver_cli import main
from archiver_exception import ArchiverFieldError
from archiver_config import GenerateConfig, LockSource, WriteAndTruncateFd
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
    # Create empty directory
    archiver.TryMakeDirs(os.path.join(TEST_DATA_PATH, 'archives'))
    archiver.TryMakeDirs(os.path.join(TEST_DATA_PATH, 'raw/report'))
    archiver.TryMakeDirs(os.path.join(TEST_DATA_PATH, 'raw/regcode'))
    os.chdir(TEST_DATA_PATH)

  def tearDown(self):
    os.chdir(self.pwd)
    try:
      shutil.rmtree(os.path.join(TEST_DATA_PATH, 'archives'))
      shutil.rmtree(os.path.join(TEST_DATA_PATH, 'raw/report'))
      shutil.rmtree(os.path.join(TEST_DATA_PATH, 'raw/regcode'))
      # Clean-up to make git status cleaner
      shutil.rmtree('raw/eventlog/20140406/.archiver')
      shutil.rmtree('raw/eventlog/20140419/.archiver')
      shutil.rmtree('raw/eventlog/20140420/.archiver')
      shutil.rmtree('raw/eventlog/20140421/.archiver')
      os.unlink('raw/eventlog/.archiver.lock')
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
    self.assertRaises(ArchiverFieldError, config.SetDuration, '86400')

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

  def _resetCopyCompleteChunksMetadata(self, completed_bytes=None):
    """Resets the metadata that solely used for CopyCompleteChunks testing.

    The metadata will be marked as all archived so other test will not be
    affected.
    """
    EVENT_LOG_PATH = os.path.join(TEST_DATA_PATH, 'raw/eventlog/20140406')
    files = ['incomplete_with_chunks',
             'incomplete_without_chunks',
             'normal_chunks']
    archiver.TryMakeDirs(
        os.path.join(EVENT_LOG_PATH, '.archiver'))
    for filename in files:
      filename = os.path.join(EVENT_LOG_PATH, filename)
      filesize = (os.path.getsize(filename) if completed_bytes is None else
                  completed_bytes)
      with open(archiver.GetMetadataPath(filename), 'w') as fd:
        WriteAndTruncateFd(
            fd, archiver.GenerateArchiverMetadata(
                completed_bytes=filesize))

  def _resetListEligibleFilesMetadata(self):
    """Resets the metadata that solely used for ListEligibleFiles testing.

    The metadata will be marked as all archived so other test will not be
    affected.
    """
    files = ['20140419/some_incomplete_bytes_appeneded',
             '20140419/no_bytes_appended',
             '20140420/corrupted_metadata_1',
             '20140420/corrupted_metadata_2',
             '20140420/corrupted_metadata_3',
             '20140421/new_created_file']

    EVENT_LOG_PATH = os.path.join(TEST_DATA_PATH, 'raw/eventlog/')
    for filename in files:
      archiver.TryMakeDirs(
          os.path.join(EVENT_LOG_PATH,
                       os.path.dirname(filename), '.archiver'))
      filename = os.path.join(EVENT_LOG_PATH, filename)
      with open(archiver.GetMetadataPath(filename), 'w') as fd:
        WriteAndTruncateFd(
            fd, archiver.GenerateArchiverMetadata(
                completed_bytes=os.path.getsize(filename)))

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
    archiver.TryMakeDirs(
        os.path.join(EVENT_LOG_PATH, '20140419/.archiver'))
    filename = os.path.join(
        EVENT_LOG_PATH, '20140419/some_incomplete_bytes_appeneded')
    with open(archiver.GetMetadataPath(filename), 'w') as fd:
      WriteAndTruncateFd(
          fd, archiver.GenerateArchiverMetadata(completed_bytes=10))
    expected_list.append((10, os.path.getsize(filename), filename))


    # Test if taken out from the returned list.
    #   raw/eventlog/20140419/no_bytes_appended
    #   raw/eventlog/20140419/.archiver/no_bytes_appeneded.metadata
    filename = os.path.join(EVENT_LOG_PATH, '20140419/no_bytes_appended')
    with open(archiver.GetMetadataPath(filename), 'w') as fd:
      WriteAndTruncateFd(
          fd, archiver.GenerateArchiverMetadata(
              completed_bytes=os.path.getsize(filename)))


    archiver.TryMakeDirs(
        os.path.join(EVENT_LOG_PATH, '20140420/.archiver'))
    # Test if metadata re-generated.
    #   1) incorrect YAML:
    #   raw/eventlog/20140420/corrupted_metadata_1
    #   raw/eventlog/20140420/.archiver/corrupted_metadata_1.metadata
    filename = os.path.join(EVENT_LOG_PATH, '20140420/corrupted_metadata_1')
    with open(archiver.GetMetadataPath(filename), 'w') as fd:
      WriteAndTruncateFd(fd, ' - where_is_my_bracket: ][')
    expected_list.append((0, os.path.getsize(filename), filename))

    #   2) valid YAML but incorrect format:
    #   raw/eventlog/20140420/corrupted_metadata_2
    #   raw/eventlog/20140420/.archiver/corrupted_metadata_2.metadata
    filename = os.path.join(EVENT_LOG_PATH, '20140420/corrupted_metadata_2')
    with open(archiver.GetMetadataPath(filename), 'w') as fd:
      WriteAndTruncateFd(fd, '- a\n- b\n- c\n')
    expected_list.append((0, os.path.getsize(filename), filename))

    #   3) valid metadata, but unreasonable completed_bytes:
    #   raw/eventlog/20140420/corrupted_metadata_3
    #   raw/eventlog/20140420/.archiver/corrupted_metadata_3.metadata
    filename = os.path.join(EVENT_LOG_PATH, '20140420/corrupted_metadata_3')
    with open(archiver.GetMetadataPath(filename), 'w') as fd:
      WriteAndTruncateFd(
          fd, archiver.GenerateArchiverMetadata(
              completed_bytes=os.path.getsize(filename) + 1))
    expected_list.append((0, os.path.getsize(filename), filename))


    # Test if metadata created automatically.
    #   raw/eventlog/20140421/new_created_file
    filename = os.path.join(EVENT_LOG_PATH, '20140421/new_created_file')
    try:
      # Make sure no metadata for this file.
      os.unlink(archiver.GetMetadataPath(filename))
    except Exception:  # pylint=disable,W0702
      pass
    expected_list.append((0, os.path.getsize(filename), filename))

    # Test if those files are skipped.
    #   raw/eventlog/20140421/creating.inprogress
    #   raw/eventlog/20140421/creating.part

    self._resetCopyCompleteChunksMetadata()
    ret_list = archiver.ListEligibleFiles(configs[0].source_dir)
    self.assertItemsEqual(expected_list, ret_list)


  def testCopyCompleteChunks(self):
    # In complete chunk at the end but still have chunks to archive.
    #    20140406/incomplete_with_chunks
    # In complete chunk at the end and no chunks to archive.
    #    20140406/incomplete_without_chunks
    # Complete chunks
    #    20140406/normal_chunks

    with open(os.path.join(TEST_DATA_PATH, 'template_eventlog.yaml')) as f:
      content = f.read()
    configs = GenerateConfig(yaml.load(content))
    config = configs[0]

    tmp_dir = tempfile.mkdtemp(prefix='FactoryArchiver',
                               suffix=config.data_type)
    logging.info('%r created for archiving data_type[%s]',
                 tmp_dir, config.data_type)
    self._resetCopyCompleteChunksMetadata(completed_bytes=0)
    self._resetListEligibleFilesMetadata()
    eligible_files = archiver.ListEligibleFiles(config.source_dir)
    archive_metadata = archiver.CopyCompleteChunks(
        eligible_files, tmp_dir, config)
    expected_return = {
        '20140406/incomplete_with_chunks': {'start': 0, 'end': 352},
        '20140406/normal_chunks': {'start': 0, 'end': 666}
        }
    self.assertDictContainsSubset(expected_return, archive_metadata['files'])
    self.assertDictContainsSubset(archive_metadata['files'], expected_return)
    shutil.rmtree(tmp_dir)
    logging.info('%r deleted', tmp_dir)

  def testCopyCompleteChunksWithoutDelimiter(self):
    # All testdata under 20140406 should be directly copied.

    with open(os.path.join(TEST_DATA_PATH, 'template_eventlog.yaml')) as f:
      content = f.read()
    configs = GenerateConfig(yaml.load(content))
    config = configs[0]
    config.SetDelimiter(None)

    tmp_dir = tempfile.mkdtemp(prefix='FactoryArchiver',
                               suffix=config.data_type)
    logging.info('%r created for archiving data_type[%s]',
                 tmp_dir, config.data_type)
    self._resetCopyCompleteChunksMetadata(completed_bytes=0)
    self._resetListEligibleFilesMetadata()
    eligible_files = archiver.ListEligibleFiles(config.source_dir)
    archive_metadata = archiver.CopyCompleteChunks(
        eligible_files, tmp_dir, config)
    expected_return = {
        '20140406/incomplete_without_chunks': {'start': 0, 'end': 311},
        '20140406/incomplete_with_chunks': {'start': 0, 'end': 411},
        '20140406/normal_chunks': {'start': 0, 'end': 666}
        }
    self.assertDictContainsSubset(expected_return, archive_metadata['files'])
    self.assertDictContainsSubset(archive_metadata['files'], expected_return)
    shutil.rmtree(tmp_dir)
    logging.info('%r deleted', tmp_dir)

  def testArchive(self):
    with open(os.path.join(TEST_DATA_PATH, 'template_eventlog.yaml')) as f:
      content = f.read()
    configs = GenerateConfig(yaml.load(content))
    config = configs[0]

    self._resetCopyCompleteChunksMetadata(completed_bytes=0)
    self._resetListEligibleFilesMetadata()

    archiver.Archive(config, next_cycle=False)

  def testCheckExecutableExistNormal(self):
    self.assertEqual(True, archiver_config.CheckExecutableExist('ls'))

  def testCheckExecutableExistFalse(self):
    self.assertEqual(
        False, archiver_config.CheckExecutableExist('DemocracyAt4AM'))

if __name__ == '__main__':
  unittest.main()
