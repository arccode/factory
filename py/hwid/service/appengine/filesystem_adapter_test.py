#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Tests for FilesystemAdapter subclasses."""

import unittest

import cloudstorage  # pylint: disable=import-error

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.appengine import appengine_test_base
from cros.factory.hwid.service.appengine import filesystem_adapter

TEST_BUCKET = 'test-bucket'
TEST_FILE = 'foo'
TEST_DATA = 'bar'
TEST_PATH = '/test-bucket/foo'


class FileSystemAdapterTest(unittest.TestCase):
  """Tests the FileSystemAdapter interface."""

  def testAbstractMethods(self):
    """Tests the expected abstract methods exist and are unimplemented."""
    fs = filesystem_adapter.FileSystemAdapter()
    # pylint: disable=protected-access
    self.assertRaises(NotImplementedError, fs._ReadFile, None)
    self.assertRaises(NotImplementedError, fs._WriteFile, None, None)
    self.assertRaises(NotImplementedError, fs._DeleteFile, None)
    self.assertRaises(NotImplementedError, fs._ListFiles, None)


class CloudStorageAdapterTest(appengine_test_base.AppEngineTestBase):
  """Tests for the CloudStorageAdapter class."""

  def setUp(self):
    super(CloudStorageAdapterTest, self).setUp()

  def testWrite(self):
    """Tests writing a file."""
    adapter = filesystem_adapter.CloudStorageAdapter(TEST_BUCKET)

    adapter.WriteFile(TEST_FILE, TEST_DATA)

    with cloudstorage.open(TEST_PATH, 'r') as fh:
      data = fh.read()

    self.assertEqual(TEST_DATA, data)

  def testRead(self):
    """Tests reading a file."""
    adapter = filesystem_adapter.CloudStorageAdapter(TEST_BUCKET)

    with cloudstorage.open(TEST_PATH, 'w') as fh:
      fh.write(TEST_DATA)

    self.assertEqual(TEST_DATA, adapter.ReadFile(TEST_FILE))

  def testDelete(self):
    """Tests deleting a file from the storage."""

    adapter = filesystem_adapter.CloudStorageAdapter(TEST_BUCKET)

    adapter.WriteFile(TEST_FILE, TEST_DATA)
    self.assertEqual(TEST_DATA, adapter.ReadFile(TEST_FILE))
    adapter.DeleteFile(TEST_FILE)

    self.assertRaises(KeyError, adapter.ReadFile, TEST_FILE)

  def testListFiles(self):
    """Tests the ListFiles method."""
    adapter = filesystem_adapter.CloudStorageAdapter(TEST_BUCKET)

    adapter.WriteFile('foo', 'bar')
    adapter.WriteFile('baz', 'qux')

    files = adapter.ListFiles()

    self.assertEqual(2, len(list(files)))

  def testListFilesFiltered(self):
    """Tests the ListFiles method with a prefix."""
    adapter = filesystem_adapter.CloudStorageAdapter(TEST_BUCKET)

    adapter.WriteFile('foo', 'bar')
    adapter.WriteFile('baz', 'qux')

    files = adapter.ListFiles(prefix='f')

    self.assertEqual(1, len(list(files)))

  def testPath(self):
    """Tests that path creation works as expected."""
    adapter = filesystem_adapter.CloudStorageAdapter(TEST_BUCKET)

    # pylint: disable=protected-access
    self.assertEqual('/' + TEST_BUCKET, adapter._GsPath())
    self.assertEqual('/' + TEST_BUCKET + '/foo', adapter._GsPath('foo'))
    self.assertEqual('/' + TEST_BUCKET + '/foo/bar',
                     adapter._GsPath('foo', 'bar'))

  def testExceptionMapper(self):
    mapper = filesystem_adapter.CloudStorageAdapter.ExceptionMapper()

    def WithError(err):
      with mapper:
        raise err

    def WithNoError():
      with mapper:
        return True

    self.assertRaises(KeyError, WithError, cloudstorage.errors.NotFoundError)
    self.assertTrue(WithNoError())


if __name__ == '__main__':
  unittest.main()
