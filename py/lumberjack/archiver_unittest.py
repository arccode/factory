#!/usr/bin/env python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Unit tests for archiver"""

# TODO(itspeter):
#  When running the test, move the whole testdata into a temporary directory
#  and dynamic inject that path into the YAML configuration to avoid affecting
#  other workflow.

import glob
import logging
import multiprocessing
import os
import shutil
import tempfile
import unittest
import yaml
import zipfile

from archiver import (Archive, EligibleFile, _IdentifyContentForArchiving,
                      _ListEligibleFiles, _Recycle)
from archiver_cli import main
from archiver_config import (ArchiverConfig, GenerateConfig, LockSource)
from archiver_exception import ArchiverFieldError
from common import (ARCHIVER_METADATA_DIRECTORY, CheckExecutableExist,
                    GenerateArchiverMetadata,
                    GetMetadataPath, GetOrCreateMetadata,
                    RegenerateArchiverMetadataFile, TryMakeDirs,
                    WriteAndTruncateFd)
from multiprocessing import Process
from subprocess import PIPE, Popen


TEST_DATA_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), 'testdata/archiver'))


class ArchiverUnittest(unittest.TestCase):
  """Unit tests for archiver."""
  pwd = None

  def setUp(self):
    logging.basicConfig(
        format=('[%(levelname)s] archiver:%(lineno)d %(asctime)s %(message)s'),
        level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')
    self.pwd = os.getcwd()
    # Create empty directory
    TryMakeDirs(os.path.join(TEST_DATA_PATH, 'archives'))
    TryMakeDirs(os.path.join(TEST_DATA_PATH, 'raw/regcode'))
    os.chdir(TEST_DATA_PATH)

  def tearDown(self):
    os.chdir(self.pwd)
    directories_to_delete = [
        'archives', 'raw/regcode',
        # Clean-up to make git status cleaner
        'raw/eventlog/20140406/.archiver', 'raw/eventlog/20140419/.archiver',
        'raw/eventlog/20140420/.archiver', 'raw/eventlog/20140421/.archiver']
    for directory in directories_to_delete:
      try:
        shutil.rmtree(os.path.join(TEST_DATA_PATH, directory))
      except:  # pylint: disable=W0702
        pass

    # Delete lock file
    lock_file_to_delete = [
        'raw/eventlog/.archiver.lock',
        'raw/report/.archiver.lock',
        'raw/.mocked_regcode.csv.archiver.lock']
    for lock_file in lock_file_to_delete:
      try:
        os.unlink(os.path.join(TEST_DATA_PATH, lock_file))
      except:  # pylint: disable=W0702
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
    self.assertRaises(ValueError, main, argv)

  def testCheckSourceFile(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'invalid_source_file.yaml')]
    self.assertRaises(ValueError, main, argv)

  def testCheckArchivedDir(self):
    argv = ['dry-run',
            os.path.join(TEST_DATA_PATH, 'invalid_archived_dir.yaml')]
    self.assertRaises(ValueError, main, argv)

  def testCheckRecycleDir(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'invalid_recycle_dir.yaml')]
    self.assertRaises(ValueError, main, argv)

  def testCheckProject(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'invalid_project.yaml')]
    self.assertRaises(ValueError, main, argv)

  def testSetDuration(self):
    argv = ['dry-run', os.path.join(TEST_DATA_PATH, 'invalid_duration.yaml')]
    self.assertRaises(ValueError, main, argv)

  def testSetDurationInternally(self):
    config = ArchiverConfig('unittest')
    # We should pass an integer instead.
    self.assertRaises(ValueError, config.SetDuration, '86400')

  def testSetCompressFormat(self):
    argv = ['dry-run',
            os.path.join(TEST_DATA_PATH, 'invalid_compress_format.yaml')]
    self.assertRaises(ValueError, main, argv)

  def testSetEncryptKeyPair(self):
    argv = ['dry-run',
            os.path.join(TEST_DATA_PATH, 'template_regcode.yaml')]
    main(argv)

  def testSetEncryptKeyPairInvalidPublicKey(self):
    argv = ['dry-run',
            os.path.join(TEST_DATA_PATH, 'invalid_publickey.yaml')]
    self.assertRaisesRegexp(
        ArchiverFieldError,
        r'Failed to encrypt with the public key .*unittest_crosreg.pub.*',
        main, argv)

  def testSetEncryptKeyPairInvalidRecipient(self):
    argv = ['dry-run',
            os.path.join(TEST_DATA_PATH, 'invalid_recipient.yaml')]
    self.assertRaisesRegexp(
        ArchiverFieldError,
        r'Failed to encrypt.* recipient.*do-evil.*',
        main, argv)

  def testSetEncryptKeyPairNoRecipient(self):
    argv = ['dry-run',
            os.path.join(TEST_DATA_PATH, 'missing_recipient.yaml')]
    main(argv)

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
    lock_completed = multiprocessing.Lock()

    def _LockSourceWrapper(run_forever=False):
      """Simple wrapper for deterministic testing result.

      The lock_completed should be acquired before calling this.

      Args:
        run_forever: True to run forever, keeping process alive.

      Returns:
        The absolute lock file path if run_forever is False.
      """
      logging.debug("Wrapper running on pid:%d", os.getpid())
      lock_path = LockSource(configs[0])
      lock_completed.release()
      logging.debug("lock_completed released, pid:%d", os.getpid())
      if run_forever:
        while True:
          pass
      return lock_path

    # Lock the first config in another process
    lock_completed.acquire()
    p = Process(target=_LockSourceWrapper, args=(True, ))
    p.start()
    # This blocks until the process had locked properly.
    lock_completed.acquire()
    self.assertRaisesRegexp(
        ArchiverFieldError, 'already monitored by another archiver',
        _LockSourceWrapper)
    # Becasuse of the exception, _LockSourceWrapper() will not release the
    # lock_completed
    lock_completed.release()

    # Test if the lock released while process terminated. If it is not, we
    # should see an exception when trying to lock the resources.
    p.terminate()  # the lock will be automatically released then.
    p.join()
    lock_completed.acquire()
    lock_path = _LockSourceWrapper()
    # Delete the temporary lock file.
    os.unlink(lock_path)

  def _ResetIdentifyContentForArchivingMetadata(self, completed_bytes=None):
    """Resets the metadata that used for _IdentifyContentForArchiving testing.

    The metadata will be marked as all archived so other test will not be
    affected.
    """
    EVENT_LOG_PATH = os.path.join(TEST_DATA_PATH, 'raw/eventlog/20140406')
    files = ['incomplete_with_chunks',
             'incomplete_without_chunks',
             'normal_chunks']
    TryMakeDirs(os.path.join(EVENT_LOG_PATH, '.archiver'))
    for filename in files:
      filename = os.path.join(EVENT_LOG_PATH, filename)
      filesize = (os.path.getsize(filename) if completed_bytes is None else
                  completed_bytes)
      with open(
          GetMetadataPath(filename, ARCHIVER_METADATA_DIRECTORY), 'w') as fd:
        WriteAndTruncateFd(
            fd, GenerateArchiverMetadata(completed_bytes=filesize))

  def _ResetListEligibleFilesMetadata(self):
    """Resets the metadata that solely used for _ListEligibleFiles testing.

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
      TryMakeDirs(
          os.path.join(EVENT_LOG_PATH,
                       os.path.dirname(filename), '.archiver'))
      filename = os.path.join(EVENT_LOG_PATH, filename)
      with open(
          GetMetadataPath(filename, ARCHIVER_METADATA_DIRECTORY), 'w') as fd:
        WriteAndTruncateFd(
            fd, GenerateArchiverMetadata(
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
    TryMakeDirs(
        os.path.join(EVENT_LOG_PATH, '20140419/.archiver'))
    filename = os.path.join(
        EVENT_LOG_PATH, '20140419/some_incomplete_bytes_appeneded')
    with open(
        GetMetadataPath(filename, ARCHIVER_METADATA_DIRECTORY), 'w') as fd:
      WriteAndTruncateFd(
          fd, GenerateArchiverMetadata(completed_bytes=10))
    expected_list.append((10, os.path.getsize(filename), filename))

    # Test if taken out from the returned list.
    #   raw/eventlog/20140419/no_bytes_appended
    #   raw/eventlog/20140419/.archiver/no_bytes_appeneded.metadata
    filename = os.path.join(EVENT_LOG_PATH, '20140419/no_bytes_appended')
    with open(
        GetMetadataPath(filename, ARCHIVER_METADATA_DIRECTORY), 'w') as fd:
      WriteAndTruncateFd(
          fd, GenerateArchiverMetadata(
              completed_bytes=os.path.getsize(filename)))

    TryMakeDirs(
        os.path.join(EVENT_LOG_PATH, '20140420/.archiver'))
    # Test if metadata re-generated.
    #   1) incorrect YAML:
    #   raw/eventlog/20140420/corrupted_metadata_1
    #   raw/eventlog/20140420/.archiver/corrupted_metadata_1.metadata
    filename = os.path.join(EVENT_LOG_PATH, '20140420/corrupted_metadata_1')
    with open(
        GetMetadataPath(filename, ARCHIVER_METADATA_DIRECTORY), 'w') as fd:
      WriteAndTruncateFd(fd, ' - where_is_my_bracket: ][')
    expected_list.append((0, os.path.getsize(filename), filename))

    #   2) valid YAML but incorrect format:
    #   raw/eventlog/20140420/corrupted_metadata_2
    #   raw/eventlog/20140420/.archiver/corrupted_metadata_2.metadata
    filename = os.path.join(EVENT_LOG_PATH, '20140420/corrupted_metadata_2')
    with open(
        GetMetadataPath(filename, ARCHIVER_METADATA_DIRECTORY), 'w') as fd:
      WriteAndTruncateFd(fd, '- a\n- b\n- c\n')
    expected_list.append((0, os.path.getsize(filename), filename))

    #   3) valid metadata, but unreasonable completed_bytes:
    #   raw/eventlog/20140420/corrupted_metadata_3
    #   raw/eventlog/20140420/.archiver/corrupted_metadata_3.metadata
    filename = os.path.join(EVENT_LOG_PATH, '20140420/corrupted_metadata_3')
    with open(
        GetMetadataPath(filename, ARCHIVER_METADATA_DIRECTORY), 'w') as fd:
      WriteAndTruncateFd(
          fd, GenerateArchiverMetadata(
              completed_bytes=os.path.getsize(filename) + 1))
    expected_list.append((0, os.path.getsize(filename), filename))

    # Test if metadata created automatically.
    #   raw/eventlog/20140421/new_created_file
    filename = os.path.join(EVENT_LOG_PATH, '20140421/new_created_file')
    try:
      # Make sure no metadata for this file.
      os.unlink(GetMetadataPath(filename, ARCHIVER_METADATA_DIRECTORY))
    except:  # pylint: disable=W0702
      pass
    expected_list.append(EligibleFile(
        last_completed_bytes=0, current_size=os.path.getsize(filename),
        full_path=filename))

    # Test if those files are skipped.
    #   raw/eventlog/20140421/creating.inprogress
    #   raw/eventlog/20140421/creating.part

    self._ResetIdentifyContentForArchivingMetadata()
    ret_list = _ListEligibleFiles(configs[0].source_dir)
    self.assertItemsEqual(expected_list, ret_list)

  def testIdentifyContentForArchiving(self):
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
    self._ResetIdentifyContentForArchivingMetadata(completed_bytes=0)
    self._ResetListEligibleFilesMetadata()
    eligible_files = _ListEligibleFiles(config.source_dir)
    archive_metadata = _IdentifyContentForArchiving(
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
    self._ResetIdentifyContentForArchivingMetadata(completed_bytes=0)
    self._ResetListEligibleFilesMetadata()
    eligible_files = _ListEligibleFiles(config.source_dir)
    archive_metadata = _IdentifyContentForArchiving(
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

    self._ResetIdentifyContentForArchivingMetadata(completed_bytes=0)
    self._ResetListEligibleFilesMetadata()

    Archive(config, next_cycle=False)
    # Check if the metadata updated as expected.
    expected_completed_bytes = [('20140406/incomplete_without_chunks', 0),
                                ('20140406/incomplete_with_chunks', 352),
                                ('20140406/normal_chunks', 666)]
    for filename, completed_bytes in expected_completed_bytes:
      metadata_path = GetMetadataPath(
          os.path.join(config.source_dir, filename),
          ARCHIVER_METADATA_DIRECTORY)
      metadata = GetOrCreateMetadata(
          metadata_path, RegenerateArchiverMetadataFile)
      self.assertEqual(completed_bytes, metadata['completed_bytes'])

  def testCheckExecutableExistNormal(self):
    self.assertEqual(True, CheckExecutableExist('ls'))

  def testCheckExecutableExistFalse(self):
    self.assertEqual(
        False, CheckExecutableExist('DemocracyAt4AM'))

  def testRecycle(self):
    # This unittest can only be ran after 20140406 + 2 days.
    with open(os.path.join(TEST_DATA_PATH, 'template_eventlog.yaml')) as f:
      content = f.read()
    configs = GenerateConfig(yaml.load(content))
    config = configs[0]

    # Prepare diectory
    self._ResetIdentifyContentForArchivingMetadata(completed_bytes=0)
    tmp_dir = tempfile.mkdtemp(
        prefix='FactoryArchiver_', suffix='_unittest')
    logging.info('%r created for Recycle() unittest', tmp_dir)
    # Inject temporary path into configuration
    config.SetDir(
        os.path.join(tmp_dir, 'raw/eventlog'), 'source_dir', create=True)
    config.SetDir(
        os.path.join(tmp_dir, 'archives'), 'archived_dir', create=True)
    config.SetDir(
        os.path.join(tmp_dir, 'recycle/raw/eventlog'),
        'recycle_dir', create=True)
    shutil.copytree(
        os.path.join(TEST_DATA_PATH, 'raw/eventlog/20140406'),
        os.path.join(tmp_dir, 'raw/eventlog/20140406'))

    # Check if the snapshot created ?
    self.assertTrue(_Recycle(config))  # Trigger snapshot creation
    self.assertTrue(
        os.path.isfile(os.path.join(
            tmp_dir, 'raw/eventlog/20140406/.archiver', '.snapshot')))
    # Check if it recycled ?
    self.assertTrue(_Recycle(config))
    self.assertFalse(
        os.path.isdir(os.path.join(tmp_dir, 'raw/eventlog/20140406')))
    self.assertTrue(
        os.path.isdir(os.path.join(tmp_dir, 'recycle/raw/eventlog/20140406')))
    # Copy the 20140406 directory again to test recycle in conflict.
    shutil.copytree(
        os.path.join(TEST_DATA_PATH, 'raw/eventlog/20140406'),
        os.path.join(tmp_dir, 'raw/eventlog/20140406'))
    self.assertTrue(_Recycle(config))  # Trigger snapshot creation
    self.assertTrue(_Recycle(config))  # Trigger conflict
    self.assertEqual(
        2, len(os.listdir(os.path.join(tmp_dir, 'recycle/raw/eventlog/'))))
    shutil.rmtree(tmp_dir)
    logging.info('%r deleted', tmp_dir)

  def testRecycleTerminatePrematurely(self):
    with open(os.path.join(TEST_DATA_PATH, 'template_regcode.yaml')) as f:
      content = f.read()
    configs = GenerateConfig(yaml.load(content))
    config = configs[0]

    self.assertFalse(_Recycle(config))

  def testArchiveRegcode(self):
    with open(os.path.join(TEST_DATA_PATH, 'template_regcode.yaml')) as f:
      content = f.read()
    configs = GenerateConfig(yaml.load(content))
    config = configs[0]

    # Prepare diectory
    tmp_dir = tempfile.mkdtemp(
        prefix='FactoryArchiver_', suffix='_unittest')
    logging.info('%r created for archiving regcode unittest', tmp_dir)
    # Create mock regcode.
    TryMakeDirs(os.path.join(tmp_dir, 'raw'))
    regcode_path = os.path.join(tmp_dir, 'raw', 'mocked_regcode.csv')
    with open(regcode_path, 'w') as fd:
      fd.write('CompletedRegCodeLine\n'
               'InCompletedLine')
    # Inject temporary path into configuration
    config.SetSourceFile(regcode_path)
    config.SetDir(
        os.path.join(tmp_dir, 'archives'), 'archived_dir', create=True)

    Archive(config, next_cycle=False)
    # Check if the metadata updated as expected.
    metadata = GetOrCreateMetadata(
        GetMetadataPath(regcode_path, ARCHIVER_METADATA_DIRECTORY),
        RegenerateArchiverMetadataFile)
    self.assertEqual(21, metadata['completed_bytes'])
    with open(regcode_path, 'a') as fd:  # Complete the delimiter
      fd.write('\n')
    Archive(config, next_cycle=False)
    metadata = GetOrCreateMetadata(
        GetMetadataPath(regcode_path, ARCHIVER_METADATA_DIRECTORY),
        RegenerateArchiverMetadataFile)
    self.assertEqual(37, metadata['completed_bytes'])

    shutil.rmtree(tmp_dir)
    logging.info('%r deleted', tmp_dir)

  def _PrepareReportsInTemporaryDir(self):
    """Prepares reports into temporary directory for unittest.

    One of the report will be marked as archived on purpose.

    Returns:
      A tuple of (temporary directory, an injected ArchiverConfig,
      a list of expected filename in archive)
    """
    with open(os.path.join(TEST_DATA_PATH, 'template_reports.yaml')) as f:
      content = f.read()
    configs = GenerateConfig(yaml.load(content))
    config = configs[0]
    # Verify the compress_in_place flag is turned on.
    self.assertTrue(config.compress_in_place)

    # Prepare diectory
    tmp_dir = tempfile.mkdtemp(
        prefix='FactoryArchiver_', suffix='_unittest')
    logging.info('%r created for Archive() reports unittest', tmp_dir)
    # Inject temporary path into configuration
    config.SetDir(
        os.path.join(tmp_dir, 'raw/report'), 'source_dir', create=True)
    config.SetDir(
        os.path.join(tmp_dir, 'archives'), 'archived_dir', create=True)
    shutil.copytree(
        os.path.join(TEST_DATA_PATH, 'raw/report/20140406'),
        os.path.join(tmp_dir, 'raw/report/20140406'))

    # Make one of the reports as archived.
    mock_archived_reports = [
        'SMT-SEL0C150GNSSC380800037-20130812T235651Z.rpt.xz',
        'SMT-SEL0C150GNSSC380800037-20130812T235651Z.rpt.xz.md5']
    for archived in mock_archived_reports:
      file_path = os.path.join(tmp_dir, 'raw/report/20140406', archived)
      # Create metadata directory
      metadata_path = GetMetadataPath(file_path, ARCHIVER_METADATA_DIRECTORY)
      GetOrCreateMetadata(metadata_path, RegenerateArchiverMetadataFile)
      with open(metadata_path, 'w') as fd:
        fd.write(GenerateArchiverMetadata(
            completed_bytes=os.path.getsize(file_path)))
    expected_files = [
        '20140406/SMT-SEL0C150GNSSC380800037-20130812T235710Z.rpt.xz',
        '20140406/SMT-SEL0C150GNSSC380800037-20130812T235710Z.rpt.xz.md5',
        '20140406/FA-3812000001-20130814T022522Z.rpt.xz',
        '20140406/FA-3812000001-20130814T022522Z.rpt.xz.md5',
        'archive.metadata']
    return (tmp_dir, config, expected_files)

  def testArchiveReports(self):
    tmp_dir, config, expected_files = self._PrepareReportsInTemporaryDir()
    # Run Archive
    Archive(config, next_cycle=False)

    # Compare the content of the archive
    zip_file_path = glob.glob(os.path.join(config.archived_dir, '*'))[0]
    archived_files = zipfile.ZipFile(zip_file_path).namelist()
    self.assertItemsEqual(expected_files, archived_files)
    shutil.rmtree(tmp_dir)
    logging.info('%r deleted', tmp_dir)

  def testArchiveReportsEncrypted(self):
    tmp_dir, config, expected_files = self._PrepareReportsInTemporaryDir()
    public_key_path = os.path.join(
        TEST_DATA_PATH, 'keys/unittest_crosreg.pub.binary')
    private_key_path = os.path.join(
        TEST_DATA_PATH, 'keys/unittest_crosreg.priv')

    config.SetEncryptKeyPair([public_key_path, 'Test Key'])
    # Run Archive
    Archive(config, next_cycle=False)

    # Try to decrypt it and verify the content
    encrypted_file_path = glob.glob(os.path.join(config.archived_dir, '*'))[0]
    cmd_line = [
        'gpg', '--batch', '--no-tty',  # Disable the tty output side effect
        '--output', encrypted_file_path[:-4], '--no-default-keyring',
        '--keyring', public_key_path, '--secret-keyring', private_key_path,
        '--trust-model', 'always', '--passphrase', 'testkey', '--decrypt',
        encrypted_file_path]

    p = Popen(cmd_line, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
      logging.error('Command %r failed. retcode[%r]\nstdout:\n%s\n\n'
                    'stderr:\n%s\n', cmd_line, p.returncode, stdout, stderr)

    # Compare the content of the archive
    archived_files = zipfile.ZipFile(encrypted_file_path[:-4]).namelist()
    self.assertItemsEqual(expected_files, archived_files)
    shutil.rmtree(tmp_dir)
    logging.info('%r deleted', tmp_dir)


if __name__ == '__main__':
  unittest.main()
