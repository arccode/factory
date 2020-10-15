#!/usr/bin/env python3
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


from datetime import date
from io import StringIO
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from cros.factory.tools import migrate_board_dir
from cros.factory.tools.migrate_board_dir import MigrateBoardException
from cros.factory.tools.migrate_board_dir import ReplacePattern
from cros.factory.utils import file_utils


def CheckFileContent(path_contents_dict):
  """Checks the contents of a list of files are as expected or not.

  Args:
    path_contents_dict: a dict of the format {'path1': 'content1',
        'path2', content2'} indicating the expected content for each file.
        A special content 'linkto: source' means a symlink pointing to source.
  """
  for path, expected_content in path_contents_dict.items():
    if expected_content.startswith('linkto:'):
      expected_linkto = expected_content.split(':')[1].strip()
      actual_linkto = os.readlink(path)
      if expected_linkto != actual_linkto:
        raise ValueError('Symlink path error (expected %r but got %r).' % (
            expected_linkto, actual_linkto))
    else:
      actual_content = file_utils.ReadFile(path)
      if expected_content != actual_content:
        raise ValueError('File content error (expected %r but got %r' % (
            expected_content, actual_content))


def CreateFileWithContent(path_contents_dict):
  """Creates a list of files with the desired content.

  Args:
    path_contents_dict: a dict of the format {'path1': 'content1',
        'path2', content2'} indicating the desired content for each file.
        A special content 'linkto: source' means creating a symlink pointing
        to source.
  """
  for path, content in path_contents_dict.items():
    if not os.path.exists(os.path.dirname(path)):
      os.makedirs(os.path.dirname(path))

    if content.startswith('linkto:'):
      linkto = content.split(':')[1].strip()
      file_utils.ForceSymlink(linkto, path)
    else:
      file_utils.WriteFile(path, content)


class PrepareDirectoryCopyTest(unittest.TestCase):

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp(prefix='migrate_board_dir_unittest')
    self.mock_instream = mock.Mock(sys.stdin)
    self.mock_outstream = StringIO()

  def tearDown(self):
    shutil.rmtree(self.temp_dir)

  def testNoSourceDirectory(self):
    nonexistent_src_dir = os.path.join(self.temp_dir, 'nonexistent_src')
    with self.assertRaises(SystemExit) as sys_exit:
      migrate_board_dir.PrepareDirectoryCopy(
          nonexistent_src_dir, mock.ANY, sys.stdin, self.mock_outstream)

    # Checks sys.exit(1) and the output messages.
    self.assertEqual(sys_exit.exception.code, 1)
    self.assertEqual(
        'Source directory: %r not found.\n' % nonexistent_src_dir,
        self.mock_outstream.getvalue())

  def testPressNToCancel(self):
    src_dir = os.path.join(self.temp_dir, 'src')
    dst_dir = os.path.join(self.temp_dir, 'dst')
    os.mkdir(src_dir)
    os.mkdir(dst_dir)

    self.mock_instream.readline = mock.Mock(return_value='n\n')
    with self.assertRaises(SystemExit) as sys_exit:
      migrate_board_dir.PrepareDirectoryCopy(src_dir, dst_dir,
                                             self.mock_instream)
    # User presses 'n' to cancel the operation.
    # Checks that dst_dir was not removed and sys.exit(0).
    self.assertTrue(os.path.exists(dst_dir))
    self.assertEqual(sys_exit.exception.code, 0)

  def testPressYToProceed(self):
    src_dir = os.path.join(self.temp_dir, 'src')
    dst_dir = os.path.join(self.temp_dir, 'dst')
    os.mkdir(src_dir)
    os.mkdir(dst_dir)

    self.mock_instream.readline = mock.Mock(return_value='y\n')
    migrate_board_dir.PrepareDirectoryCopy(
        src_dir, dst_dir, self.mock_instream, self.mock_outstream)
    # User presses 'y' to remove the dst_dir.
    # Checks that dst_dir was removed.
    self.assertFalse(os.path.exists(dst_dir))
    self.assertTrue(self.mock_outstream.getvalue().endswith(
        'Directory: %r was removed before migration.\n' % dst_dir))


class CopyFilesAndRenameTest(unittest.TestCase):

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp(prefix='migrate_board_dir_unittest')

  def tearDown(self):
    shutil.rmtree(self.temp_dir)

  def testCopyFilesAndRenameSuccess(self):
    src_dir = os.path.join(self.temp_dir, 'src')
    dst_dir = os.path.join(self.temp_dir, 'dst')
    src_files = {
        os.path.join(src_dir, 'test-0.0.1.ebuild'): 'Test ebuild file.',
        os.path.join(src_dir, 'dog_file1'): 'Test file.',
    }
    src_symlink_files = {
        os.path.join(src_dir, 'test-0.0.1-r100.ebuild'):
            'linkto: ./test-0.0.1.ebuild',
        os.path.join(src_dir, 'dog_folder', 'dog_file2'):
            'linkto: ../dog_file1',
    }
    expected_dst_files = {
        os.path.join(dst_dir, 'test-0.0.1.ebuild'):
            'Test ebuild file.',
        os.path.join(dst_dir, 'cat_file1'):
            'Test file.',
        os.path.join(dst_dir, 'test-0.0.1-r1.ebuild'):
            'linkto: ./test-0.0.1.ebuild',
        os.path.join(dst_dir, 'cat_folder', 'cat_file2'):
            'linkto: ../cat_file1',
    }

    CreateFileWithContent(src_files)
    CreateFileWithContent(src_symlink_files)
    migrate_board_dir.CopyFilesAndRename(
        src_dir,
        dst_dir,
        ReplacePattern('dog', 'cat'),  # Renames 'dog' to 'cat' in file names.
        reset_ebuild_file=True)
    CheckFileContent(expected_dst_files)

  @mock.patch('shutil.copystat')
  @mock.patch('shutil.copy2')
  def testCopyFilesAndRenameWithFailure(self, copy2_mock, copystat_mock):
    src_dir = os.path.join(self.temp_dir, 'src')
    dst_dir = os.path.join(self.temp_dir, 'dst')
    src_files = {
        os.path.join(src_dir, 'no_such_file1'): 'No such file1.',
        os.path.join(src_dir, 'dog_folder', 'no_such_file2'): 'No such file2.',
        os.path.join(src_dir, 'dog_file3'): 'Test file3.',
    }
    CreateFileWithContent(src_files)

    errors = []  # Stores the error for all file operations.

    # Exception happens for no_such_file in the root folder.
    no_src_file = os.path.join(src_dir, 'no_such_file1')
    no_dst_file = os.path.join(dst_dir, 'no_such_file1')
    no_such_file_raised_exception = IOError(
        'IOError: [Errno 2] No such file or directory: %r' % no_src_file)
    errors.append((no_src_file, no_dst_file,
                   str(no_such_file_raised_exception)))

    # Exception happens for no_such_file2 in the sub folder.
    src_sub_dir = os.path.join(src_dir, 'dog_folder')
    dst_sub_dir = os.path.join(dst_dir, 'cat_folder')
    no_src_file2 = os.path.join(src_sub_dir, 'no_such_file2')
    no_dst_file2 = os.path.join(dst_sub_dir, 'no_such_file2')
    no_such_file2_raised_exception = IOError(
        'IOError: [Errno 2] No such file or directory: %r' % no_src_file2)
    errors.append((no_src_file2, no_dst_file2,
                   str(no_such_file2_raised_exception)))

    # Test copystat error.
    raised_exception = OSError(
        'OSError: [Errno 2] No such file or directory: %r' % src_dir)
    errors.append((src_dir, dst_dir, str(raised_exception)))

    # Normal files should still be copied and renamed as expected.
    normal_src_file = os.path.join(src_dir, 'dog_file3')
    normal_dst_file = os.path.join(dst_dir, 'cat_file3')

    def Copy2SideEffect(*args, **unused_kwargs):
      if args[0] == no_src_file and args[1] == no_dst_file:
        raise no_such_file_raised_exception
      if args[0] == no_src_file2 and args[1] == no_dst_file2:
        raise no_such_file2_raised_exception
      if args[0] == normal_src_file and args[1] == normal_dst_file:
        return 0
      return None

    def CopystatSideEffect(*args, **unused_kwargs):
      # The sub folder should be copied and renamed as expected.
      if args[0] == src_sub_dir and args[1] == dst_sub_dir:
        return 0
      # Test copystat error.
      if args[0] == src_dir and args[1] == dst_dir:
        raise raised_exception
      return None

    copy2_mock.side_effect = Copy2SideEffect
    copystat_mock.side_effect = CopystatSideEffect

    with self.assertRaises(MigrateBoardException) as context_manager:
      migrate_board_dir.CopyFilesAndRename(
          src_dir,
          dst_dir,
          ReplacePattern('dog', 'cat'),  # Renames 'dog' to 'cat' in file names.
          reset_ebuild_file=True)
    # Checks it includes all errors raised from recursive call in the exception.
    self.assertEqual(set(context_manager.exception.args[0]), set(errors))

    copy2_mock.assert_any_call(no_src_file, no_dst_file)
    copy2_mock.assert_any_call(no_src_file2, no_dst_file2)
    copy2_mock.assert_any_call(normal_src_file, normal_dst_file)
    self.assertEqual(3, copy2_mock.call_count)

    copystat_mock.assert_any_call(src_sub_dir, dst_sub_dir)
    copystat_mock.assert_any_call(src_dir, dst_dir)
    self.assertEqual(2, copystat_mock.call_count)


class ReplaceStringInFilesTest(unittest.TestCase):

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp(prefix='migrate_board_dir_unittest')

  def tearDown(self):
    shutil.rmtree(self.temp_dir)

  def testReplaceString(self):
    # Checks the following rename patterns:
    # 1. dog -> cat
    # 2. Dog -> Cat
    # 3. DOG -> CAT
    content1_before = """\
This is a dog.
Dog is man's best friend.
WATCH OUT FOR THE DOGS!!!"""
    content1_after = """\
This is a cat.
Cat is man's best friend.
WATCH OUT FOR THE CATS!!!"""

    # Checks the year in the license header will be updated.
    # Also checks that (c) is removed.
    content2_before = """\
# Copyright 2013 (c) The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file."""
    content2_after = """\
# Copyright %d The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.""" % date.today().year

    files_before_replacement = {
        os.path.join(self.temp_dir, 'file1'): content1_before,
        os.path.join(self.temp_dir, 'sub_folder', 'file2'): content2_before,
    }
    files_after_replacement = {
        os.path.join(self.temp_dir, 'file1'): content1_after,
        os.path.join(self.temp_dir, 'sub_folder', 'file2'): content2_after,
    }

    CreateFileWithContent(files_before_replacement)
    migrate_board_dir.ReplaceStringInFiles(
        self.temp_dir,
        migrate_board_dir.GenerateReplacePatterns('dog', 'cat'))
    CheckFileContent(files_after_replacement)


if __name__ == '__main__':
  unittest.main()
