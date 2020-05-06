#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Tests for CloudStorageAdapter"""

import unittest

import cloudstorage  # pylint: disable=import-error

from cros.factory.hwid.service.appengine import appengine_test_base
from cros.factory.hwid.service.appengine import cloudstorage_adapter


TEST_BUCKET = 'test-bucket'
TEST_FILE = 'foo'
TEST_DATA = 'bar'
TEST_PATH = '/test-bucket/foo'


class CloudStorageAdapterTest(appengine_test_base.AppEngineTestBase):
  """Tests for the CloudStorageAdapter class."""

  def testWrite(self):
    """Tests writing a file."""
    adapter = cloudstorage_adapter.CloudStorageAdapter(TEST_BUCKET)

    adapter.WriteFile(TEST_FILE, TEST_DATA)

    with cloudstorage.open(TEST_PATH, 'r') as fh:
      data = fh.read()

    self.assertEqual(TEST_DATA, data)

  def testRead(self):
    """Tests reading a file."""
    adapter = cloudstorage_adapter.CloudStorageAdapter(TEST_BUCKET)

    with cloudstorage.open(TEST_PATH, 'w') as fh:
      fh.write(TEST_DATA)

    self.assertEqual(TEST_DATA, adapter.ReadFile(TEST_FILE))

  def testDelete(self):
    """Tests deleting a file from the storage."""

    adapter = cloudstorage_adapter.CloudStorageAdapter(TEST_BUCKET)

    adapter.WriteFile(TEST_FILE, TEST_DATA)
    self.assertEqual(TEST_DATA, adapter.ReadFile(TEST_FILE))
    adapter.DeleteFile(TEST_FILE)

    self.assertRaises(KeyError, adapter.ReadFile, TEST_FILE)

  def testListFiles(self):
    """Tests the ListFiles method."""
    adapter = cloudstorage_adapter.CloudStorageAdapter(TEST_BUCKET)

    adapter.WriteFile('foo', 'bar')
    adapter.WriteFile('baz', 'qux')

    files = adapter.ListFiles()

    self.assertEqual(2, len(list(files)))

  def testListFilesFiltered(self):
    """Tests the ListFiles method with a prefix (directory)."""
    adapter = cloudstorage_adapter.CloudStorageAdapter(TEST_BUCKET)

    adapter.WriteFile('foo/bar/file', 'bar')
    adapter.WriteFile('foo/baz/file', 'bar')
    adapter.WriteFile('foo/file0', 'bar')
    adapter.WriteFile('foo/file1', 'bar')
    adapter.WriteFile('foo1', 'bar')
    adapter.WriteFile('baz', 'qux')

    files = adapter.ListFiles(prefix='f')

    self.assertFalse(list(files))

    prefix_wo_trailing_slash = sorted(list(adapter.ListFiles(prefix='foo')))
    prefix_w_trailing_slash = sorted(list(adapter.ListFiles(prefix='foo/')))
    self.assertEqual(prefix_w_trailing_slash, prefix_wo_trailing_slash)
    self.assertEqual(prefix_w_trailing_slash, ['file0', 'file1'])

  def testPath(self):
    """Tests that path creation works as expected."""
    adapter = cloudstorage_adapter.CloudStorageAdapter(TEST_BUCKET)

    # pylint: disable=protected-access
    self.assertEqual('/' + TEST_BUCKET, adapter._GsPath())
    self.assertEqual('/' + TEST_BUCKET + '/foo', adapter._GsPath('foo'))
    self.assertEqual('/' + TEST_BUCKET + '/foo/bar',
                     adapter._GsPath('foo', 'bar'))

  def testExceptionMapper(self):
    mapper = cloudstorage_adapter.CloudStorageAdapter.ExceptionMapper()

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
