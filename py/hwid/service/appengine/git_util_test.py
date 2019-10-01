#!/usr/bin/env python2
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for cros.factory.hwid.service.appengine.git_util"""

import datetime
import httplib
import unittest

# pylint: disable=import-error, no-name-in-module
from dulwich.objects import Tree
import mock
from six import assertRegex

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.appengine import git_util


# pylint: disable=protected-access
class GitUtilTest(unittest.TestCase):

  def testAddFiles(self):
    new_files = [
        ('a/b/c', 0o100644, 'content of a/b/c'),
        ('///a/b////d', 0o100644, 'content of a/b/d'),
        ('a/b/e/./././f', 0o100644, 'content of a/b/e/f'),
        ]
    repo = git_util.MemoryRepo('')
    tree = Tree()
    try:
      tree, unused_new_obj_ids = repo.add_files(new_files, tree)
      tree.check()
    except Exception as ex:
      self.fail("testAddFiles raise Exception unexpectedly: %r" % ex)

    mode1, sha1 = tree.lookup_path(repo.get_object, 'a/b/c')
    self.assertEqual(mode1, 0o100644)
    self.assertEqual(repo[sha1].data, 'content of a/b/c')

    mode2, sha2 = tree.lookup_path(repo.get_object, 'a/b/d')
    self.assertEqual(mode2, 0o100644)
    self.assertEqual(repo[sha2].data, 'content of a/b/d')

    mode3, sha3 = tree.lookup_path(repo.get_object, 'a/b/e/f')
    self.assertEqual(mode3, 0o100644)
    self.assertEqual(repo[sha3].data, 'content of a/b/e/f')

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
        ('a/b/c', 0o100644, 'content of a/b/c'),
        ('a/b/c/d', 0o100644, 'content of a/b/c/d'),
        ]
    repo = git_util.MemoryRepo('')
    tree = Tree()
    with self.assertRaises(git_util.GitUtilException) as ex:
      repo.add_files(new_files, tree)
    self.assertEqual(str(ex.exception), "Invalid filepath 'a/b/c/d'")

  def testInvalidFileStructure2(self):
    new_files = [
        ('a/b/c/d', 0o100644, 'content of a/b/c/d'),
        ('a/b/c', 0o100644, 'content of a/b/c'),
        ]
    repo = git_util.MemoryRepo('')
    tree = Tree()
    with self.assertRaises(git_util.GitUtilException) as ex:
      repo.add_files(new_files, tree)
    self.assertEqual(str(ex.exception), "Invalid filepath 'a/b/c'")

  def testGetCommitId(self):
    git_url_prefix = 'https://chromium-review.googlesource.com'
    project = 'chromiumos/platform/factory'
    branch = 'master'

    auth_cookie = ''  # auth_cookie is not needed in chromium repo
    commit = git_util.GetCommitId(git_url_prefix, project, branch, auth_cookie)
    assertRegex(self, commit, '^[0-9a-f]{40}$')

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
        mock.MagicMock(status=httplib.BAD_REQUEST, data=''),
        # invalid json
        mock.MagicMock(status=httplib.OK, data=(
            ")]}'\n"
            '\n'
            '  "revision": "0123456789abcdef0123456789abcdef01234567"\n'
            '}\n')),
        # no magic line
        mock.MagicMock(status=httplib.OK, data=(
            '{\n'
            '  "revision": "0123456789abcdef0123456789abcdef01234567"\n'
            '}\n')),
        # no "revision" field
        mock.MagicMock(status=httplib.OK, data=(
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
        branch='master')
    tree = repo[repo['HEAD'].tree]
    unused_size, object_id = tree[file_name]
    new_files = [(file_name, 0o100644, repo[object_id].data)]
    self.assertRaises(
        git_util.GitUtilNoModificationException,
        git_util.CreateCL,
        'https://chromium.googlesource.com/chromiumos/platform/factory',
        '',
        'chromiumos/platform/factory',
        'master',
        new_files,
        'John Doe <no-reply@google.com>',
        'John Doe <no-reply@google.com>',
        '')


if __name__ == '__main__':
  unittest.main()
