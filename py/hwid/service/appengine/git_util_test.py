#!/usr/bin/env python3
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for cros.factory.hwid.service.appengine.git_util"""

import datetime
import hashlib
import http.client
import os.path
import unittest
from unittest import mock

# pylint: disable=wrong-import-order, import-error
from dulwich.objects import Tree
# pylint: enable=wrong-import-order, import-error

from cros.factory.hwid.service.appengine import git_util
from cros.factory.hwid.v3 import filesystem_adapter


# pylint: disable=protected-access
class GitUtilTest(unittest.TestCase):

  def testAddFiles(self):
    new_files = [
        ('a/b/c', 0o100644, b'content of a/b/c'),
        ('///a/b////d', 0o100644, b'content of a/b/d'),
        ('a/b/e/./././f', 0o100644, b'content of a/b/e/f'),
        ]
    repo = git_util.MemoryRepo('')
    tree = Tree()
    try:
      tree = repo.add_files(new_files, tree)
      tree.check()
    except Exception as ex:
      self.fail("testAddFiles raise Exception unexpectedly: %r" % ex)

    mode1, sha1 = tree.lookup_path(repo.get_object, b'a/b/c')
    self.assertEqual(mode1, 0o100644)
    self.assertEqual(repo[sha1].data, b'content of a/b/c')

    mode2, sha2 = tree.lookup_path(repo.get_object, b'a/b/d')
    self.assertEqual(mode2, 0o100644)
    self.assertEqual(repo[sha2].data, b'content of a/b/d')

    mode3, sha3 = tree.lookup_path(repo.get_object, b'a/b/e/f')
    self.assertEqual(mode3, 0o100644)
    self.assertEqual(repo[sha3].data, b'content of a/b/e/f')

  @mock.patch('cros.factory.hwid.service.appengine.git_util.datetime')
  def testGetChangeId(self, datetime_mock):
    """Reference result of expected implementation."""

    datetime_mock.datetime.now.return_value = datetime.datetime.fromtimestamp(
        1556616237)
    tree_id = '4e7b52cf7c0b196914c924114c7225333f549bf1'
    parent = '3ef27b7a56e149a7cc64aaf1af837248daac514e'
    author = 'change-id test <change-id-test@google.com>'
    committer = 'change-id test <change-id-test@google.com>'
    commit_msg = 'Change Id test'
    expected_change_id = 'I3b5a06d980966aaa3d981ecb4d578f0cc1dd8179'
    change_id = git_util._GetChangeId(
        tree_id, parent, author, committer,
        commit_msg)
    self.assertEqual(change_id, expected_change_id)

  def testInvalidFileStructure1(self):
    new_files = [
        ('a/b/c', 0o100644, b'content of a/b/c'),
        ('a/b/c/d', 0o100644, b'content of a/b/c/d'),
        ]
    repo = git_util.MemoryRepo('')
    tree = Tree()
    with self.assertRaises(git_util.GitUtilException) as ex:
      repo.add_files(new_files, tree)
    self.assertEqual(str(ex.exception), "Invalid filepath 'a/b/c/d'")

  def testInvalidFileStructure2(self):
    new_files = [
        ('a/b/c/d', 0o100644, b'content of a/b/c/d'),
        ('a/b/c', 0o100644, b'content of a/b/c'),
        ]
    repo = git_util.MemoryRepo('')
    tree = Tree()
    with self.assertRaises(git_util.GitUtilException) as ex:
      repo.add_files(new_files, tree)
    self.assertEqual(str(ex.exception), "Invalid filepath 'a/b/c'")

  def testGetCommitId(self):
    git_url_prefix = 'https://chromium-review.googlesource.com'
    project = 'chromiumos/platform/factory'
    branch = None

    auth_cookie = ''  # auth_cookie is not needed in chromium repo
    commit = git_util.GetCommitId(git_url_prefix, project, branch, auth_cookie)
    self.assertRegex(commit, '^[0-9a-f]{40}$')

  @mock.patch('cros.factory.hwid.service.appengine.git_util.PoolManager')
  def testGetCommitIdFormatError(self, mocked_poolmanager):
    """Mock response and status to test if exceptions are raised."""
    git_url_prefix = 'dummy'
    project = 'dummy'
    branch = 'dummy'
    auth_cookie = 'dummy'

    instance = mocked_poolmanager.return_value  # pool_manager instance
    error_responses = [
        # 400 error
        mock.MagicMock(status=http.client.BAD_REQUEST, data=''),
        # invalid json
        mock.MagicMock(status=http.client.OK, data=(
            ")]}'\n"
            '\n'
            '  "revision": "0123456789abcdef0123456789abcdef01234567"\n'
            '}\n')),
        # no magic line
        mock.MagicMock(status=http.client.OK, data=(
            '{\n'
            '  "revision": "0123456789abcdef0123456789abcdef01234567"\n'
            '}\n')),
        # no "revision" field
        mock.MagicMock(status=http.client.OK, data=(
            ")]}'\n"
            '{\n'
            '  "no_revision": "0123456789abcdef0123456789abcdef01234567"\n'
            '}\n')),
        ]

    for resp in error_responses:
      instance.urlopen.return_value = resp
      self.assertRaises(
          git_util.GitUtilException, git_util.GetCommitId, git_url_prefix,
          project, branch, auth_cookie)

  def testNoModification(self):
    file_name = 'README.md'
    repo = git_util.MemoryRepo(auth_cookie='')
    repo.shallow_clone(
        'https://chromium.googlesource.com/chromiumos/platform/factory',
        branch='stabilize-rust-13562.B')
    tree = repo[repo[b'HEAD'].tree]
    unused_size, object_id = tree[file_name.encode()]
    new_files = [(file_name, 0o100644, repo[object_id].data)]
    self.assertRaises(
        git_util.GitUtilNoModificationException, git_util.CreateCL,
        'https://chromium.googlesource.com/chromiumos/platform/factory', '',
        'stabilize-rust-13562.B', new_files, 'John Doe <no-reply@google.com>',
        'John Doe <no-reply@google.com>', '')

  def testListFiles(self):
    new_files = [
        ('a/b/c', 0o100644, b'content of a/b/c'),
        ('///a/b////d', 0o100644, b'content of a/b/d'),
        ('a/b/e/./././f', 0o100644, b'content of a/b/e/f'),
        ]
    repo = git_util.MemoryRepo('')
    tree = Tree()
    try:
      tree = repo.add_files(new_files, tree)
      tree.check()
    except Exception as ex:
      self.fail("testListFiles raise Exception unexpectedly: %r" % ex)
    repo.do_commit(b'Test_commit', tree=tree.id)

    self.assertEqual(sorted(repo.list_files('a/b')),
                     [('c', git_util.NORMAL_FILE_MODE, b'content of a/b/c'),
                      ('d', git_util.NORMAL_FILE_MODE, b'content of a/b/d'),
                      ('e', git_util.DIR_MODE, None)])


class GitFilesystemAdapterTest(unittest.TestCase):
  def setUp(self):
    self.repo = git_util.MemoryRepo(auth_cookie='')
    self.repo.shallow_clone(
        'https://chromium.googlesource.com/chromiumos/platform/factory',
        branch='stabilize-13360.B')  # use a stabilize branch as a repo snapshot
    self.git_fs = git_util.GitFilesystemAdapter(self.repo)
    self.target_dir = 'deploy'
    self.file_name = 'README.md'
    self.file_path = os.path.join(self.target_dir, self.file_name)

  def testListFiles(self):
    self.assertIn(self.file_name, self.git_fs.ListFiles(self.target_dir))

  def testReadFile(self):
    # Validate the consistency between content hash and object hash in git.
    content = self.git_fs.ReadFile(self.file_path)
    head_commit = self.repo[b'HEAD']
    unused_mode, sha = self.repo[head_commit.tree].lookup_path(
        self.repo.get_object, self.file_path.encode())
    self.assertEqual(
        sha.decode(), hashlib.sha1(
            (b'blob %d\x00%b' % (len(content), content))).hexdigest())

  def testReadOnly(self):
    # Test if GitFilesystemAdapter is unsupported for WriteFile and DeleteFile.
    self.assertRaises(
        filesystem_adapter.FileSystemAdapterException,
        self.git_fs.WriteFile, self.file_path, b'')
    self.assertRaises(
        filesystem_adapter.FileSystemAdapterException,
        self.git_fs.DeleteFile, self.file_path)


if __name__ == '__main__':
  unittest.main()
