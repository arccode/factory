#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Tests for CloudStorageAdapter"""

import collections
import os.path
import unittest
from unittest import mock

import google.cloud.exceptions  # pylint: disable=no-name-in-module, import-error

from cros.factory.hwid.service.appengine import cloudstorage_adapter

TEST_BUCKET = 'test-bucket'
TEST_FILE = 'foo'
TEST_DATA = b'bar'
TEST_PATH = '/test-bucket/foo'


def _CreateMockListBlobsWrapper(test_files):
  blob_class = collections.namedtuple('Blob', ['name', 'path'])
  def wrapper(bucket_name, prefix, delimiter):
    if bucket_name == TEST_BUCKET and delimiter == '/':
      if prefix == '':
        return [blob_class(name=key, path=None) for key in test_files
                if os.path.dirname(key) == prefix]
      return [blob_class(name=key, path=None) for key in test_files
              if os.path.dirname(key) + '/' == prefix]
    return []
  return wrapper


# TODO(clarkchung): Use official cloud storage emulator when it is available.
class CloudStorageAdapterTest(unittest.TestCase):
  """Tests for the CloudStorageAdapter class."""

  def setUp(self):
    super(CloudStorageAdapterTest, self).setUp()
    patcher = mock.patch('__main__.cloudstorage_adapter.storage')
    self.mock_storage = patcher.start()
    self.addCleanup(patcher.stop)

  def testWrite(self):
    """Tests writing a file."""
    adapter = cloudstorage_adapter.CloudStorageAdapter(TEST_BUCKET)

    adapter.WriteFile(TEST_FILE, TEST_DATA)
    mock_blob = self.mock_storage.Client().bucket().blob
    mock_blob.assert_has_calls([mock.call(TEST_FILE),
                                mock.call().upload_from_string(TEST_DATA)])


  def testRead(self):
    """Tests reading a file."""
    adapter = cloudstorage_adapter.CloudStorageAdapter(TEST_BUCKET)
    mock_blob = self.mock_storage.Client().bucket().blob
    mock_blob().download_as_string.return_value = TEST_DATA
    read_result = adapter.ReadFile(TEST_FILE)
    mock_blob.assert_has_calls([mock.call(TEST_FILE),
                                mock.call().download_as_string()])
    self.assertEqual(TEST_DATA, read_result)

  def testDelete(self):
    """Tests deleting a file from the storage."""

    adapter = cloudstorage_adapter.CloudStorageAdapter(TEST_BUCKET)

    mock_blob = self.mock_storage.Client().bucket().blob
    adapter.WriteFile(TEST_FILE, TEST_DATA)
    adapter.DeleteFile(TEST_FILE)
    mock_blob.assert_has_calls([mock.call(TEST_FILE),
                                mock.call().delete()])
    mock_blob().download_as_string.side_effect = \
        google.cloud.exceptions.NotFound('Not found')
    self.assertRaises(KeyError, adapter.ReadFile, TEST_FILE)

  def testListFiles(self):
    """Tests the ListFiles method."""
    adapter = cloudstorage_adapter.CloudStorageAdapter(TEST_BUCKET)

    test_files = {
        'foo': b'bar',
        'baz': b'qux',
        }

    mock_client = self.mock_storage.Client()
    mock_client.list_blobs.side_effect = _CreateMockListBlobsWrapper(test_files)

    for path, content in test_files.items():
      adapter.WriteFile(path, content)

    files = adapter.ListFiles()

    self.assertEqual(sorted(files), sorted(test_files))

  def testListFilesFiltered(self):
    """Tests the ListFiles method with a prefix (directory)."""
    adapter = cloudstorage_adapter.CloudStorageAdapter(TEST_BUCKET)

    test_files = {
        'foo/bar/file': b'bar',
        'foo/baz/file': b'bar',
        'foo/file0': b'bar',
        'foo/file1': b'bar',
        'foo1': b'bar',
        'baz': b'qux',
        }

    mock_client = self.mock_storage.Client()
    mock_client.list_blobs.side_effect = _CreateMockListBlobsWrapper(test_files)

    for path, content in test_files.items():
      adapter.WriteFile(path, content)

    files = adapter.ListFiles(prefix='f')

    self.assertFalse(list(files))

    prefix_wo_trailing_slash = sorted(list(adapter.ListFiles(prefix='foo')))
    prefix_w_trailing_slash = sorted(list(adapter.ListFiles(prefix='foo/')))
    self.assertEqual(prefix_w_trailing_slash, prefix_wo_trailing_slash)
    self.assertEqual(prefix_w_trailing_slash, ['file0', 'file1'])

  def testExceptionMapper(self):
    mapper = cloudstorage_adapter.CloudStorageAdapter.ExceptionMapper()

    def WithError(err):
      with mapper:
        raise err

    def WithNoError():
      with mapper:
        return True

    self.assertRaises(KeyError, WithError,
                      google.cloud.exceptions.NotFound('Not Found'))
    self.assertTrue(WithNoError())


if __name__ == '__main__':
  unittest.main()
