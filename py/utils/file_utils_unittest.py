#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for file_utils.py."""

import binascii
import logging
import mock
import mox
import multiprocessing
import os
import re
import shutil
import tempfile
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils import file_utils


class MakeDirsUidGidTest(unittest.TestCase):
  FILE_PERMISSION_MASK = 0777

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()

  def tearDown(self):
    shutil.rmtree(self.temp_dir)

  def GetPermissionBits(self, path):
    return os.stat(path).st_mode & self.FILE_PERMISSION_MASK

  def testDefault(self):
    target_path = os.path.join(self.temp_dir, 'foo', 'bar', 'baz')
    file_utils.MakeDirsUidGid(target_path)
    path_to_check = self.temp_dir
    for tail in ['foo', 'bar', 'baz']:
      path_to_check = os.path.join(path_to_check, tail)
      self.assertEqual(0777, self.GetPermissionBits(path_to_check))

  def testMode(self):
    target_path = os.path.join(self.temp_dir, 'foo', 'bar', 'baz')
    mode = 0770
    file_utils.MakeDirsUidGid(target_path, mode=mode)
    path_to_check = self.temp_dir
    for tail in ['foo', 'bar', 'baz']:
      path_to_check = os.path.join(path_to_check, tail)
      self.assertEqual(mode, self.GetPermissionBits(path_to_check))

  def testEmpty(self):
    file_utils.MakeDirsUidGid('')

  def testNoSlash(self):
    cwd = os.getcwd()
    os.chdir(self.temp_dir)

    file_utils.MakeDirsUidGid('foo')
    self.assertTrue(os.path.isdir(os.path.join(self.temp_dir, 'foo')))

    os.chdir(cwd)

  def testRelative(self):
    cwd = os.getcwd()
    os.chdir(self.temp_dir)

    file_utils.MakeDirsUidGid(os.path.join('foo', 'bar'))
    self.assertTrue(os.path.isdir(os.path.join(self.temp_dir, 'foo', 'bar')))

    os.chdir(cwd)


class UnopenedTemporaryFileTest(unittest.TestCase):
  """Unittest for UnopenedTemporaryFile."""
  def testUnopenedTemporaryFile(self):
    with file_utils.UnopenedTemporaryFile(
        prefix='prefix', suffix='suffix') as x:
      self.assertTrue(os.path.exists(x))
      self.assertEquals(0, os.path.getsize(x))
      assert re.match('prefix.+suffix', os.path.basename(x))
      self.assertEquals(tempfile.gettempdir(), os.path.dirname(x))
    self.assertFalse(os.path.exists(x))


class ReadLinesTest(unittest.TestCase):
  """Unittest for ReadLines."""
  def testNormalFile(self):
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.write('line 1\nline 2\n')
    tmp.close()
    try:
      lines = file_utils.ReadLines(tmp.name)
      self.assertEquals(len(lines), 2)
      self.assertEquals(lines[0], 'line 1\n')
      self.assertEquals(lines[1], 'line 2\n')
    finally:
      os.unlink(tmp.name)

  def testEmptyFile(self):
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    try:
      lines = file_utils.ReadLines(tmp.name)
      self.assertTrue(isinstance(lines, list))
      self.assertEquals(len(lines), 0)
    finally:
      os.unlink(tmp.name)

  def testNonExistFile(self):
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    os.unlink(tmp.name)

    lines = file_utils.ReadLines(tmp.name)
    self.assertTrue(lines is None)


class TempDirectoryTest(unittest.TestCase):
  """Unittest for TempDirectory."""
  def testNormal(self):
    with file_utils.TempDirectory(prefix='abc') as d:
      self.assertTrue(os.path.basename(d).startswith('abc'))
      self.assertTrue(os.path.isdir(d))
    self.assertFalse(os.path.exists(d))

  def testRemoveBeforeExit(self):
    with file_utils.TempDirectory() as d:
      self.assertTrue(os.path.isdir(d))
      shutil.rmtree(d)
      self.assertFalse(os.path.exists(d))
    self.assertFalse(os.path.exists(d))

  def testRenameBeforeExit(self):
    with file_utils.TempDirectory() as d:
      self.assertTrue(os.path.isdir(d))
      new_name = d + '.another'
      os.rename(d, new_name)
    self.assertFalse(os.path.exists(d))
    self.assertTrue(os.path.exists(new_name))
    shutil.rmtree(new_name)


class PrependFileTest(unittest.TestCase):
  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()

  def tearDown(self):
    shutil.rmtree(self.temp_dir)

  def testPrependFile(self):
    test_file = os.path.join(self.temp_dir, 'test')
    file_utils.WriteFile(test_file, 'line 1\nline 2')

    file_utils.PrependFile(test_file, 'header 1\nheader 2\n')
    self.assertEqual('header 1\nheader 2\nline 1\nline 2',
                     file_utils.Read(test_file))

  def testPrependEmptyFile(self):
    test_file = os.path.join(self.temp_dir, 'test')

    file_utils.PrependFile(test_file, 'header 1\nheader 2\n')
    self.assertEqual('header 1\nheader 2\n',
                     file_utils.Read(test_file))


class CopyFileSkipBytesTest(unittest.TestCase):
  """Unittest for CopyFileSkipBytes."""
  def setUp(self):
    self.in_file = None
    self.out_file = None

  def tearDown(self):
    if self.in_file:
      os.unlink(self.in_file.name)
    if self.out_file:
      os.unlink(self.out_file.name)

  def PrepareFile(self, in_file_content, out_file_content):
    self.in_file = tempfile.NamedTemporaryFile(delete=False)
    if in_file_content:
      self.in_file.write(in_file_content)
    self.in_file.close()
    self.out_file = tempfile.NamedTemporaryFile(delete=False)
    if out_file_content:
      self.out_file.write(out_file_content)
    self.out_file.close()

  def testNormal(self):
    self.PrepareFile('1234567890', '')
    file_utils.CopyFileSkipBytes(self.in_file.name, self.out_file.name, 3)
    with open(self.out_file.name, 'r') as o:
      result = o.read()
      self.assertEquals(result, '4567890')

  def testSkipTooMany(self):
    self.PrepareFile('1234567890', '')
    # Skip too many bytes.
    self.assertRaises(ValueError, file_utils.CopyFileSkipBytes,
                      self.in_file.name, self.out_file.name, 100)
    with open(self.out_file.name, 'r') as o:
      self.assertEquals(len(o.read()), 0)

  def testNoInput(self):
    self.PrepareFile('abc', '')
    self.assertRaises(OSError, file_utils.CopyFileSkipBytes,
                      'no_input', self.out_file.name, 1)

  def testOverrideOutput(self):
    self.PrepareFile('1234567890', 'abcde')
    file_utils.CopyFileSkipBytes(self.in_file.name, self.out_file.name, 3)
    with open(self.out_file.name, 'r') as o:
      result = o.read()
      self.assertEquals(result, '4567890')

  def testSkipLargeFile(self):
    # 10000 bytes input.
    self.PrepareFile('1234567890' * 1000, '')
    file_utils.CopyFileSkipBytes(self.in_file.name, self.out_file.name, 5)
    with open(self.out_file.name, 'r') as o:
      result = o.read()
      self.assertEquals(len(result), 10000 - 5)
      self.assertTrue(result.startswith('67890'))


class ExtractFileTest(unittest.TestCase):
  """Unit tests for ExtractFile."""
  @mock.patch.object(file_utils, 'Spawn', return_value=True)
  def testExtractZip(self, mock_spawn):
    file_utils.ExtractFile('foo.zip', 'foo_dir')
    mock_spawn.assert_called_with(['unzip', '-o', 'foo.zip', '-d', 'foo_dir'],
                                  log=True, check_call=True)

    file_utils.ExtractFile('foo.zip', 'foo_dir', quiet=True)
    mock_spawn.assert_called_with(['unzip', '-o', '-qq', 'foo.zip',
                                   '-d', 'foo_dir'], log=True, check_call=True)

    file_utils.ExtractFile('foo.zip', 'foo_dir', only_extracts=['bar', 'buz'])
    mock_spawn.assert_called_with(['unzip', '-o', 'foo.zip', '-d', 'foo_dir',
                                   'bar', 'buz'], log=True, check_call=True)

    file_utils.ExtractFile('foo.zip', 'foo_dir', only_extracts=['bar', 'buz'],
                           overwrite=False)
    mock_spawn.assert_called_with(['unzip', 'foo.zip', '-d', 'foo_dir',
                                   'bar', 'buz'], log=True, check_call=True)

  @mock.patch.object(file_utils, 'Spawn', return_value=True)
  def testExtractTar(self, mock_spawn):
    file_utils.ExtractFile('foo.tar.gz', 'foo_dir')
    mock_spawn.assert_called_with(['tar', '-xf', 'foo.tar.gz', '-vv', '-C',
                                   'foo_dir'], log=True, check_call=True)

    file_utils.ExtractFile('foo.tar.gz', 'foo_dir', quiet=True)
    mock_spawn.assert_called_with(['tar', '-xf', 'foo.tar.gz', '-C',
                                   'foo_dir'], log=True, check_call=True)

    file_utils.ExtractFile('foo.tbz2', 'foo_dir', only_extracts=['bar', 'buz'])
    mock_spawn.assert_called_with(['tar', '-xf', 'foo.tbz2', '-vv',
                                   '-C', 'foo_dir', 'bar', 'buz'],
                                  log=True, check_call=True)

    file_utils.ExtractFile('foo.tar.xz', 'foo_dir', only_extracts='bar',
                           overwrite=False)
    mock_spawn.assert_called_with(['tar', '-xf', '--keep-old-files',
                                   'foo.tar.xz', '-vv', '-C', 'foo_dir', 'bar'],
                                  log=True, check_call=True)

class ForceSymlinkTest(unittest.TestCase):
  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()

  def tearDown(self):
    shutil.rmtree(self.temp_dir)

  def testNoTarget(self):
    self.assertRaisesRegexp(Exception, 'Missing symlink target',
                            file_utils.ForceSymlink, '/foo/non_exist_target',
                            '/foo/non_exist_link')
  def testNormal(self):
    target_path = os.path.join(self.temp_dir, 'target')
    link_path = os.path.join(self.temp_dir, 'link_to_target')
    file_utils.WriteFile(target_path, 'target')

    file_utils.ForceSymlink(target_path, link_path)

    self.assertTrue(target_path, os.path.realpath(link_path))
    self.assertTrue('target', file_utils.ReadLines(link_path)[0])

  def testForceOverwrite(self):
    target_path = os.path.join(self.temp_dir, 'target')
    link_path = os.path.join(self.temp_dir, 'link_to_target')
    file_utils.WriteFile(target_path, 'target')
    file_utils.WriteFile(link_path, 'something else')

    file_utils.ForceSymlink(target_path, link_path)

    self.assertTrue(target_path, os.path.realpath(link_path))
    self.assertTrue('target', file_utils.ReadLines(link_path)[0])


class AtomicCopyTest(unittest.TestCase):
  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()

  def tearDown(self):
    shutil.rmtree(self.temp_dir)

  def testNoSource(self):
    self.assertRaisesRegexp(IOError, 'Missing source',
                            file_utils.AtomicCopy,
                            '/foo/non_exist_source', '/foo/non_exist_dest')
    self.assertFalse(os.path.exists('/foo/non_exist_source'))
    self.assertFalse(os.path.exists('/foo/non_exist_dest'))

  def testNormal(self):
    source_path = os.path.join(self.temp_dir, 'source')
    dest_path = os.path.join(self.temp_dir, 'dest')
    file_utils.WriteFile(source_path, 'source')
    self.assertFalse(os.path.exists(dest_path))

    file_utils.AtomicCopy(source_path, dest_path)

    self.assertTrue(os.path.exists(dest_path))
    self.assertEqual('source', file_utils.ReadLines(dest_path)[0])

  def testOverwrite(self):
    source_path = os.path.join(self.temp_dir, 'source')
    dest_path = os.path.join(self.temp_dir, 'dest')
    file_utils.WriteFile(source_path, 'source')
    file_utils.WriteFile(dest_path, 'dest')

    file_utils.AtomicCopy(source_path, dest_path)

    # dest is overwritten.
    self.assertEqual('source', file_utils.ReadLines(dest_path)[0])


  def testCopyFailed(self):
    m = mox.Mox()
    m.StubOutWithMock(shutil, 'copy2')

    source_path = os.path.join(self.temp_dir, 'source')
    dest_path = os.path.join(self.temp_dir, 'dest')

    file_utils.WriteFile(source_path, 'source')
    file_utils.WriteFile(dest_path, 'dest')

    shutil.copy2(source_path, mox.IgnoreArg()).AndRaise(IOError)
    m.ReplayAll()

    self.assertRaises(IOError, file_utils.AtomicCopy, source_path,
                      dest_path)
    # Verify that dest file is unchanged after a failed copy.
    self.assertEqual('dest', file_utils.ReadLines(dest_path)[0])

    m.UnsetStubs()
    m.VerifyAll()


class Md5sumInHexTest(unittest.TestCase):
  def runTest(self):
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_file.write('Md5sumInHex test')
    temp_file.close()
    self.assertEqual('a7edf9375e036698a408c9777de1ebd1',
                     file_utils.Md5sumInHex(temp_file.name))
    os.unlink(temp_file.name)


class FileLockTest(unittest.TestCase):
  def setUp(self):
    self.temp_file = tempfile.mkstemp()[1]

  def tearDown(self):
    os.unlink(self.temp_file)

  def testFileLockMultiProcess(self):
    def Target():
      file_utils.FileLock(self.temp_file).Acquire()
      time.sleep(2)

    p = multiprocessing.Process(target=Target)
    p.start()
    time.sleep(0.5)
    self.assertRaisesRegexp(
        IOError, r'Resource temporarily unavailable',
        file_utils.FileLock(self.temp_file).Acquire)
    p.terminate()

  def testFileLockMultiProcessWithTimeout(self):
    def Target(idle_secs):
      lock = file_utils.FileLock(self.temp_file)
      lock.Acquire()
      time.sleep(idle_secs)
      lock.Release()

    # One process hold lock for 1 second, and another wait for the lock for at
    # most 3 seconds.
    p = multiprocessing.Process(target=lambda: Target(1))
    p.start()
    time.sleep(0.5)
    lock = file_utils.FileLock(self.temp_file, timeout_secs=3)
    # These two Acquire() and Release() calls should not raise exception.
    lock.Acquire()
    lock.Release()
    p.terminate()

    # One process hold lock for 3 seconds, and another wait for the lock for at
    # most 1 second.
    p = multiprocessing.Process(target=lambda: Target(3))
    p.start()
    time.sleep(0.5)
    lock = file_utils.FileLock(self.temp_file, timeout_secs=1)
    self.assertRaisesRegexp(
        file_utils.FileLockTimeoutError,
        r'Could not acquire file lock of .* in 1 second\(s\)',
        lock.Acquire)
    p.terminate()

  def testFileLockSingleProcess(self):
    # Lock and unlock a file twice.
    with file_utils.FileLock(self.temp_file):
      pass
    lock = file_utils.FileLock(self.temp_file)
    # These two Acquire() and Release() calls should not raise exception.
    lock.Acquire()
    lock.Release()

    # Try to grab lock on a locked file.
    file_utils.FileLock(self.temp_file).Acquire()
    self.assertRaisesRegexp(
        IOError, r'Resource temporarily unavailable',
        file_utils.FileLock(self.temp_file).Acquire)

  def testFileLockSingleProcessWithTimeout(self):
    file_utils.FileLock(self.temp_file).Acquire()
    self.assertRaisesRegexp(
        file_utils.FileLockTimeoutError,
        r'Could not acquire file lock of .* in 1 second\(s\)',
        file_utils.FileLock(self.temp_file, timeout_secs=1).Acquire)


class ReadWriteFileTest(unittest.TestCase):
  def runTest(self):
    with file_utils.UnopenedTemporaryFile() as tmp:
      data = 'abc\n\0'
      file_utils.WriteFile(tmp, data)
      self.assertEquals(data, file_utils.ReadFile(tmp))


class GlobSingleFileTest(unittest.TestCase):
  def runTest(self):
    with file_utils.TempDirectory() as d:
      for f in ('a', 'b'):
        file_utils.TouchFile(os.path.join(d, f))

      self.assertEquals(
          os.path.join(d, 'a'),
          file_utils.GlobSingleFile(os.path.join(d, '[a]')))
      self.assertRaisesRegexp(
          ValueError,
          r"Expected one match for .+/\* but got "
          r"\['.+/(a|b)', '.+/(a|b)'\]",
          file_utils.GlobSingleFile, os.path.join(d, '*'))
      self.assertRaisesRegexp(
          ValueError,
          r"Expected one match for .+/nomatch but got \[\]",
          file_utils.GlobSingleFile, os.path.join(d, 'nomatch'))


class HashFilesTest(unittest.TestCase):
  def setUp(self):
    self.tmpdir = tempfile.mkdtemp(prefix='HashFilesTest.')

    for relpath in ['a', 'b', 'c', 'd/e', 'd/f']:
      path = os.path.join(self.tmpdir, relpath)
      file_utils.TryMakeDirs(os.path.dirname(path))
      file_utils.WriteFile(path, 'Contents of %s' % relpath)

    # ...and create a symlink cc -> c (it should be skipped)
    os.symlink('c', os.path.join(self.tmpdir, 'cc'))

  def tearDown(self):
    shutil.rmtree(self.tmpdir)

  def testDefault(self):
    self.assertEquals({
          'a': 'fbd313f05f277535c6f0bb2e9b0cff43cebef360',
          'b': '1ac13620623e6ff9049a7a261e04dda284b2c52a',
          'c': 'eef64cf8244577e292e46fc6a12e64261239d972',
          'd/e': '585a50860871f4df30be233ace89b3c83f776c9b',
          'd/f': '025b55bbf9d628147696b63970edca695109e9ba'
          }, file_utils.HashFiles(self.tmpdir))

  def testSimpleHash(self):
    self.assertEquals({
          'a': 2937989080,
          'b': 907507298,
          'c': 1091585780,
          'd/e': 2218600652,
          'd/f': 489978230
          }, file_utils.HashFiles(
              self.tmpdir,
              hash_function=lambda data: binascii.crc32(data) & 0xffffffff))

  def testFilter(self):
    # Get checksum only everything but 'c'.
    self.assertEquals({
          'a': 'fbd313f05f277535c6f0bb2e9b0cff43cebef360',
          'b': '1ac13620623e6ff9049a7a261e04dda284b2c52a',
          'd/e': '585a50860871f4df30be233ace89b3c83f776c9b',
          'd/f': '025b55bbf9d628147696b63970edca695109e9ba'
        }, file_utils.HashFiles(
            self.tmpdir,
            path_filter=lambda path: path != os.path.join(self.tmpdir, 'c')))

if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  unittest.main()
