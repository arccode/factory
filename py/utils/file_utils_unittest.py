#!/usr/bin/env python2
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for file_utils.py."""

import base64
import binascii
import hashlib
import logging
import multiprocessing
import os
import re
import shutil
import tempfile
import threading
import time
import unittest

import mock
import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


class MakeDirsUidGidTest(unittest.TestCase):
  FILE_PERMISSION_MASK = 0o777

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
      self.assertEqual(0o777, self.GetPermissionBits(path_to_check))

  def testMode(self):
    target_path = os.path.join(self.temp_dir, 'foo', 'bar', 'baz')
    mode = 0o770
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
      assert re.match(r'prefix.+suffix', os.path.basename(x))
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

  def testNormalFileWithDUT(self):
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.write('line 1\nline 2\n')
    tmp.close()
    try:
      lines = file_utils.ReadLines(tmp.name, device_utils.CreateDUTInterface())
      self.assertEquals(len(lines), 2)
      self.assertEquals(lines[0], 'line 1\n')
      self.assertEquals(lines[1], 'line 2\n')
    finally:
      os.unlink(tmp.name)

  def testEmptyFileWithDUT(self):
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    try:
      lines = file_utils.ReadLines(tmp.name, device_utils.CreateDUTInterface())
      self.assertTrue(isinstance(lines, list))
      self.assertEquals(len(lines), 0)
    finally:
      os.unlink(tmp.name)

  def testNonExistFileWithDUT(self):
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    os.unlink(tmp.name)

    lines = file_utils.ReadLines(tmp.name, device_utils.CreateDUTInterface())
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
                     file_utils.ReadFile(test_file))

  def testPrependEmptyFile(self):
    test_file = os.path.join(self.temp_dir, 'test')

    file_utils.PrependFile(test_file, 'header 1\nheader 2\n')
    self.assertEqual('header 1\nheader 2\n',
                     file_utils.ReadFile(test_file))


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
  @mock.patch.object(process_utils, 'Spawn', return_value=True)
  def testExtractZip(self, mock_spawn):
    with file_utils.TempDirectory() as temp_dir:
      zipfile = os.path.join(temp_dir, 'foo.zip')
      file_utils.TouchFile(zipfile)
      output_dir = os.path.join(temp_dir, 'extracted')

      file_utils.ExtractFile(zipfile, output_dir)
      mock_spawn.assert_called_with(['unzip', '-o', zipfile, '-d', output_dir],
                                    log=True, check_call=True)

      file_utils.ExtractFile(zipfile, output_dir, quiet=True)
      mock_spawn.assert_called_with(
          ['unzip', '-o', '-qq', zipfile, '-d', output_dir],
          log=True, check_call=True)

      file_utils.ExtractFile(zipfile, output_dir, only_extracts=['bar', 'buz'])
      mock_spawn.assert_called_with(['unzip', '-o', zipfile, '-d', output_dir,
                                     'bar', 'buz'], log=True, check_call=True)

      file_utils.ExtractFile(zipfile, output_dir, only_extracts=['bar', 'buz'],
                             overwrite=False)
      mock_spawn.assert_called_with(
          ['unzip', zipfile, '-d', output_dir, 'bar', 'buz'],
          log=True, check_call=True)

  @mock.patch.object(os, 'system', return_value=0)
  @mock.patch.object(process_utils, 'Spawn', return_value=True)
  def testExtractTar(self, mock_spawn, mock_system):
    with file_utils.TempDirectory() as temp_dir:
      output_dir = os.path.join(temp_dir, 'extracted')

      targz = os.path.join(temp_dir, 'foo.tar.gz')
      file_utils.TouchFile(targz)
      file_utils.ExtractFile(targz, output_dir)
      mock_spawn.assert_called_with(
          ['tar', '-xf', targz, '-C', output_dir, '-vv'],
          log=True, check_call=True)

      file_utils.ExtractFile(targz, output_dir, quiet=True)
      mock_spawn.assert_called_with(['tar', '-xf', targz, '-C', output_dir],
                                    log=True, check_call=True)

      tbz2 = os.path.join(temp_dir, 'foo.tbz2')
      file_utils.TouchFile(tbz2)
      file_utils.ExtractFile(tbz2, output_dir, only_extracts=['bar', 'buz'])
      mock_spawn.assert_called_with(
          ['tar', '-xf', tbz2, '-C', output_dir, '-vv', 'bar', 'buz'],
          log=True, check_call=True)

      xz = os.path.join(temp_dir, 'foo.tar.xz')
      file_utils.TouchFile(xz)
      file_utils.ExtractFile(xz, output_dir, only_extracts='bar',
                             overwrite=False)
      mock_spawn.assert_called_with(
          ['tar', '-xf', xz, '-C', output_dir, '--keep-old-files', '-vv',
           'bar'],
          log=True, check_call=True)

      file_utils.ExtractFile(tbz2, output_dir, use_parallel=True)
      mock_system.assert_called_with('type lbzip2 >/dev/null 2>&1')
      mock_spawn.assert_has_calls([
          mock.call(
              ['tar', '-xf', tbz2, '-C', output_dir, '-vv', '-I', 'lbzip2'],
              log=True, check_call=True)])

  def testMissingCompressFile(self):
    self.assertRaisesRegexp(file_utils.ExtractFileError,
                            'Missing compressed file',
                            file_utils.ExtractFile, 'itdoesnotexist', 'foo_dir')

  def testPermissionDenied(self):
    with file_utils.TempDirectory() as temp_dir:
      targz = os.path.join(temp_dir, 'foo.tar.gz')
      file_utils.TouchFile(targz)
      output_dir = os.path.join(temp_dir, 'extracted')
      try:
        os.chmod(targz, 0)
        self.assertRaisesRegexp(
            file_utils.ExtractFileError, 'Permission denied',
            file_utils.ExtractFile, targz, output_dir)
      finally:
        os.chmod(targz, 0o600)


class ForceSymlinkTest(unittest.TestCase):

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()

  def tearDown(self):
    shutil.rmtree(self.temp_dir)

  def testNoTarget(self):
    target_path = os.path.join(self.temp_dir, 'non_exist_target')
    link_path = os.path.join(self.temp_dir, 'link_to_target')

    self.assertRaisesRegexp(Exception, 'Missing symlink target',
                            file_utils.ForceSymlink, target_path, link_path)

  def testNormal(self):
    target_path = os.path.join(self.temp_dir, 'target')
    link_path = os.path.join(self.temp_dir, 'link_to_target')
    file_utils.WriteFile(target_path, 'target')

    file_utils.ForceSymlink(target_path, link_path)

    self.assertEquals(target_path, os.path.realpath(link_path))
    self.assertEquals('target', file_utils.ReadLines(link_path)[0])

  def testForceOverwrite(self):
    target_path = os.path.join(self.temp_dir, 'target')
    link_path = os.path.join(self.temp_dir, 'link_to_target')
    file_utils.WriteFile(target_path, 'target')
    file_utils.WriteFile(link_path, 'something else')

    file_utils.ForceSymlink(target_path, link_path)

    self.assertEquals(target_path, os.path.realpath(link_path))
    self.assertEquals('target', file_utils.ReadLines(link_path)[0])

  def testRelativeSymlink(self):
    absolute_target_path = os.path.join(self.temp_dir, 'target')
    relative_target_path = 'target'
    link_path = os.path.join(self.temp_dir, 'link_to_target')
    file_utils.WriteFile(absolute_target_path, 'target')

    file_utils.ForceSymlink(relative_target_path, link_path)

    self.assertEquals(absolute_target_path, os.path.realpath(link_path))
    self.assertEquals('target', file_utils.ReadLines(link_path)[0])


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


class FileHashTest(unittest.TestCase):

  def setUp(self):
    self.test_string = 'FileHash test'
    f = tempfile.NamedTemporaryFile(delete=False)
    self.temp_file = f.name
    f.write(self.test_string)
    f.close()

  def tearDown(self):
    os.unlink(self.temp_file)

  def testFileHash(self):
    self.assertEqual(file_utils.FileHash(self.temp_file, 'md5').hexdigest(),
                     file_utils.MD5InHex(self.temp_file))
    self.assertEqual('5e8c0fb0a780eff4947e1d76cfc5ee27',
                     file_utils.MD5InHex(self.temp_file))
    self.assertEqual('XowPsKeA7/SUfh12z8XuJw==',
                     file_utils.MD5InBase64(self.temp_file))
    self.assertEqual('e7c60cc7247d49ffcac5f7db0176ad7ad5f9795f',
                     file_utils.SHA1InHex(self.temp_file))
    self.assertEqual('58YMxyR9Sf/KxffbAXatetX5eV8=',
                     file_utils.SHA1InBase64(self.temp_file))

  def testMultiBlockHash(self):
    with open(self.temp_file, 'rb') as f:
      with mock.patch('__builtin__.open', mock.mock_open()) as m:
        m_file = m.return_value
        m_file.read.side_effect = f.read

        # Test with 1 block.
        block_size = len(self.test_string)
        one_ret = file_utils.FileHash(
            self.temp_file, 'md5', block_size=block_size).hexdigest()
        m_file.read.assert_has_calls([mock.call(block_size)] * 2)
        f.seek(0)

        # Test with 2 blocks.
        block_size = len(self.test_string) / 2 + 1
        two_ret = file_utils.FileHash(
            self.temp_file, 'md5', block_size=block_size).hexdigest()
        m_file.read.assert_has_calls([mock.call(block_size)] * 3)
        f.seek(0)

        self.assertEqual(one_ret, two_ret)

  def testLegacyMatchesMD5InHex(self):
    # Legacy method calculates the hash all at once.
    old_hash = hashlib.md5(open(self.temp_file, 'rb').read()).hexdigest()
    new_hash = file_utils.MD5InHex(self.temp_file)
    self.assertEqual(old_hash, new_hash)

  def testLegacyMatchesSHA1InBase64(self):
    # Legacy method calculates the hash all at once.
    old_hash = base64.standard_b64encode(hashlib.sha1(
        open(self.temp_file, 'rb').read()).digest())
    new_hash = file_utils.SHA1InBase64(self.temp_file)
    self.assertEqual(old_hash, new_hash)


class FileLockTest(unittest.TestCase):

  def setUp(self):
    self.temp_file = file_utils.CreateTemporaryFile()

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

  def testLocksReleaseFileDescriptor(self):
    for _ in xrange(3333):
      c = file_utils.FileLock(self.temp_file)
      c.Acquire()
      c.Release()


class FileLockContextManagerTest(unittest.TestCase):
  def setUp(self):
    self.temp_file = file_utils.CreateTemporaryFile()
    self.manager = file_utils.FileLockContextManager(self.temp_file, 'w')

  def tearDown(self):
    os.unlink(self.temp_file)

  def testMultithreadClose(self):
    start_event = threading.Event()
    def Target():
      with self.manager as f:
        start_event.set()
        f.write('!' * 1024 * 1024)
    t = threading.Thread(target=Target)
    t.start()
    start_event.wait()
    self.manager.Close()


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
          r'Expected one match for .+/\* but got '
          r"\['.+/(a|b)', '.+/(a|b)'\]",
          file_utils.GlobSingleFile, os.path.join(d, '*'))
      self.assertRaisesRegexp(
          ValueError,
          r'Expected one match for .+/nomatch but got \[\]',
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


class AtomicWriteTest(unittest.TestCase):
  """Unittests for AtomicWrite."""

  def setUp(self):
    self.tmp_dir = tempfile.mkdtemp(prefix='AtomicWriteTest.')
    # Store the current working directory for restoring in tearDown.
    self.orig_cwd = os.getcwd()
    os.chdir(self.tmp_dir)

  def tearDown(self):
    os.chdir(self.orig_cwd)
    shutil.rmtree(self.tmp_dir)

  def testCurrentDirectory(self):
    with file_utils.AtomicWrite('dummy'):
      pass

  def testRelativePathWithDirectory(self):
    """Tests using a relative path with a file contained in a subdirectory."""
    SUBDIR_NAME = 'subdir'
    WRITE_STRING = 'Hello World!'
    os.mkdir(SUBDIR_NAME)
    path = os.path.join(SUBDIR_NAME, 'atomic_write_file')
    with file_utils.AtomicWrite(path) as f:
      f.write(WRITE_STRING)
    self.assertEqual(WRITE_STRING, file_utils.ReadOneLine(path))

  def testNonExistentDirectoryPath(self):
    """Tests using a path to a directory that doesn't exist."""
    with self.assertRaises(AssertionError):
      with file_utils.AtomicWrite('dir/'):
        pass

  def testExistingDirectoryPath(self):
    """Tests using a path to a directory that does exist."""
    SUBDIR_NAME = 'subdir'
    os.mkdir(SUBDIR_NAME)
    with self.assertRaises(OSError):
      with file_utils.AtomicWrite(SUBDIR_NAME):
        pass


class SymlinkRelativeTest(unittest.TestCase):
  """Unittests for SymlinkRelative."""

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()
    self.target = os.path.join(self.temp_dir, 'foo', 'target')
    self.link_path = None
    file_utils.TryMakeDirs(os.path.dirname(self.target))
    file_utils.TouchFile(self.target)

  def tearDown(self):
    if os.path.isdir(self.temp_dir):
      shutil.rmtree(self.temp_dir)

  def SymlinkRelativeAndVerify(self, **kwargs):
    file_utils.TryMakeDirs(os.path.dirname(self.link_path))
    file_utils.SymlinkRelative(self.target, self.link_path, **kwargs)
    self.assertEqual(os.path.realpath(self.link_path), self.target)

  def testNormal(self):
    self.link_path = os.path.join(self.temp_dir, 'bar', 'link')
    self.SymlinkRelativeAndVerify()
    self.assertFalse(os.path.isabs(os.readlink(self.link_path)))

  def testForce(self):
    self.link_path = os.path.join(self.temp_dir, 'link')
    file_utils.TouchFile(self.link_path)

    with self.assertRaises(OSError):
      self.SymlinkRelativeAndVerify()

    self.SymlinkRelativeAndVerify(force=True)

  def testBaseBothInside(self):
    self.link_path = os.path.join(self.temp_dir, 'bar', 'link')
    self.SymlinkRelativeAndVerify(base=self.temp_dir)
    self.assertFalse(os.path.isabs(os.readlink(self.link_path)))

  def testBaseLinkNotInside(self):
    self.link_path = os.path.join(self.temp_dir, 'bar', 'link')
    self.SymlinkRelativeAndVerify(base=os.path.join(self.temp_dir, 'foo'))
    self.assertTrue(os.path.isabs(os.readlink(self.link_path)))

  def testBaseTargetNotInside(self):
    self.link_path = os.path.join(self.temp_dir, 'bar', 'link')
    self.SymlinkRelativeAndVerify(base=os.path.join(self.temp_dir, 'bar'))
    self.assertTrue(os.path.isabs(os.readlink(self.link_path)))

  def testBaseBothNotInside(self):
    self.link_path = os.path.join(self.temp_dir, 'fux', 'link')
    self.SymlinkRelativeAndVerify(base=os.path.join(self.temp_dir, 'f'))
    self.assertTrue(os.path.isabs(os.readlink(self.link_path)))

  def testTargetAlreadyRelative(self):
    self.link_path = os.path.join(self.temp_dir, 'bar', 'link')
    file_utils.TryMakeDirs(os.path.dirname(self.link_path))
    file_utils.SymlinkRelative('../foo/target', self.link_path)
    self.assertEqual(os.path.realpath(self.link_path), self.target)
    self.assertFalse(os.path.isabs(os.readlink(self.link_path)))


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  unittest.main()
