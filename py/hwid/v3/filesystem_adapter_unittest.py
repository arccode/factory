#!/usr/bin/env python3
#
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import os.path
import tempfile
import unittest

from cros.factory.hwid.v3 import filesystem_adapter
from cros.factory.utils import file_utils


TEST_FILE = 'foo'
TEST_DATA = 'bar'


class FileSystemAdapterTest(unittest.TestCase):
  """Tests the FileSystemAdapter interface."""

  def testAbstractClass(self):
    """Tests if FileSystemAdapter cannot be instantiated since it's an abstract
    class."""
    self.assertRaises(TypeError, filesystem_adapter.FileSystemAdapter)


class LocalFileSystemAdapterTest(unittest.TestCase):
  """Tests the LocalFileSystemAdapter class."""

  def setUp(self):
    self.base = tempfile.mkdtemp()

  def testWrite(self):
    """Tests writing a file."""
    adapter = filesystem_adapter.LocalFileSystemAdapter(self.base)
    adapter.WriteFile(TEST_FILE, TEST_DATA)
    filepath = os.path.join(self.base, TEST_FILE)
    data = file_utils.ReadFile(filepath)
    self.assertEqual(TEST_DATA, data)

  def testRead(self):
    """Tests reading a file."""
    adapter = filesystem_adapter.LocalFileSystemAdapter(self.base)

    file_utils.WriteFile(os.path.join(self.base, TEST_FILE), TEST_DATA)

    self.assertEqual(TEST_DATA, adapter.ReadFile(TEST_FILE))

  def testDelete(self):
    """Tests deleting a file from the storage."""
    adapter = filesystem_adapter.LocalFileSystemAdapter(self.base)

    adapter.WriteFile(TEST_FILE, TEST_DATA)
    self.assertEqual(TEST_DATA, adapter.ReadFile(TEST_FILE))
    adapter.DeleteFile(TEST_FILE)

    self.assertRaises(filesystem_adapter.FileSystemAdapterException,
                      adapter.ReadFile, TEST_FILE)

  def testListFiles(self):
    """Tests the ListFiles method."""
    adapter = filesystem_adapter.LocalFileSystemAdapter(self.base)

    adapter.WriteFile('foo', 'bar')
    adapter.WriteFile('baz', 'qux')

    files = adapter.ListFiles()

    self.assertEqual(sorted(files), ['baz', 'foo'])

  def testListFilesFiltered(self):
    """Tests the ListFiles method with a prefix."""
    adapter = filesystem_adapter.LocalFileSystemAdapter(self.base)
    prefix_path1 = tempfile.mkdtemp(dir=self.base)
    prefix_base1 = os.path.basename(prefix_path1)

    prefix_path2 = tempfile.mkdtemp(dir=self.base)
    prefix_base2 = os.path.basename(prefix_path2)

    adapter.WriteFile('bar', 'foo')
    adapter.WriteFile(os.path.join(prefix_base1, 'foo1'), 'bar')
    adapter.WriteFile(os.path.join(prefix_base1, 'baz1'), 'qux')
    adapter.WriteFile(os.path.join(prefix_base2, 'foo2'), 'bar')
    adapter.WriteFile(os.path.join(prefix_base2, 'baz2'), 'qux')

    files = adapter.ListFiles(prefix=prefix_base1)
    self.assertEqual(sorted(files), ['baz1', 'foo1'])

    files = adapter.ListFiles(prefix=prefix_base2)
    self.assertEqual(sorted(files), ['baz2', 'foo2'])

  def testExceptionMapper(self):
    mapper = filesystem_adapter.LocalFileSystemAdapter.EXCEPTION_MAPPER

    def WithError(err):
      with mapper:
        raise err

    def WithoutError():
      with mapper:
        return True

    self.assertRaises(filesystem_adapter.FileSystemAdapterException, WithError,
                      OSError)
    self.assertRaises(filesystem_adapter.FileSystemAdapterException, WithError,
                      IOError)
    self.assertTrue(WithoutError())


if __name__ == '__main__':
  unittest.main()
