#!/usr/bin/env python3
# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import os
import unittest
from unittest import mock

from cros.factory.hwid.service.appengine import git_util
from cros.factory.hwid.service.appengine import hwid_repo
from cros.factory.utils import file_utils


_SERVER_BOARDS_YAML = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'testdata/boards_server.yaml')
_SERVER_BOARDS_DATA = file_utils.ReadFile(_SERVER_BOARDS_YAML, encoding=None)


class HWIDRepoTest(unittest.TestCase):

  def setUp(self):
    self._mock_git_fs = mock.create_autospec(git_util.GitFilesystemAdapter,
                                             instance=True)
    self._hwid_repo = hwid_repo.HWIDRepo(self._mock_git_fs)

  def testIterNamePatterns(self):
    self._mock_git_fs.ListFiles.side_effect = collections.defaultdict(
        list, {
            'name_pattern': ['pattern1.yaml', 'pattern2.yaml']
        }).__getitem__
    self._mock_git_fs.ReadFile.side_effect = {
        'name_pattern/pattern1.yaml': b'pattern1',
        'name_pattern/pattern2.yaml': b'pattern2',
    }.__getitem__

    actual_name_patterns = list(self._hwid_repo.IterNamePatterns())

    expected_name_patterns = [
        ('pattern1.yaml', 'pattern1'),
        ('pattern2.yaml', 'pattern2'),
    ]
    self.assertCountEqual(actual_name_patterns, expected_name_patterns)

  def testIterAVLNameMappings(self):
    self._mock_git_fs.ListFiles.side_effect = collections.defaultdict(
        list, {
            'avl_name_mapping': ['comp_category1.yaml', 'comp_category2.yaml']
        }).__getitem__
    self._mock_git_fs.ReadFile.side_effect = {
        'avl_name_mapping/comp_category1.yaml': b'pattern1',
        'avl_name_mapping/comp_category2.yaml': b'pattern2',
    }.__getitem__

    actual_avl_name_mappings = list(self._hwid_repo.IterAVLNameMappings())

    expected_avl_name_mappings = [
        ('comp_category1.yaml', 'pattern1'),
        ('comp_category2.yaml', 'pattern2'),
    ]
    self.assertCountEqual(actual_avl_name_mappings, expected_avl_name_mappings)

  def testListHWIDDBMetadata_Success(self):
    self._mock_git_fs.ReadFile.side_effect = {
        'projects.yaml': _SERVER_BOARDS_DATA
    }.__getitem__

    actual_hwid_db_metadata_list = self._hwid_repo.ListHWIDDBMetadata()

    expected_hwid_db_metadata_list = [
        hwid_repo.HWIDDBMetadata('KBOARD', 'KBOARD', 2, 'KBOARD'),
        hwid_repo.HWIDDBMetadata('KBOARD.old', 'KBOARD', 2, 'KBOARD.old'),
        hwid_repo.HWIDDBMetadata('SBOARD', 'SBOARD', 3, 'SBOARD'),
        hwid_repo.HWIDDBMetadata('COOLCBOARD', 'COOLCBOARD', 3, 'COOLCBOARD'),
        hwid_repo.HWIDDBMetadata('BETTERCBOARD', 'BETTERCBOARD', 3,
                                 'BETTERCBOARD'),
    ]
    self.assertCountEqual(actual_hwid_db_metadata_list,
                          expected_hwid_db_metadata_list)

  def testListHWIDDBMetadata_InvalidProjectYaml(self):
    self._mock_git_fs.ReadFile.side_effect = {
        'projects.yaml': ':this_is_not_an_invalid_data ^.<'
    }.__getitem__

    with self.assertRaises(hwid_repo.HWIDRepoError):
      self._hwid_repo.ListHWIDDBMetadata()

  def testLoadHWIDDBByName_Success(self):
    self._mock_git_fs.ReadFile.side_effect = {
        'projects.yaml': _SERVER_BOARDS_DATA,
        'SBOARD': b'sboard data'
    }.__getitem__

    actual_hwid_db = self._hwid_repo.LoadHWIDDBByName('SBOARD')
    self.assertCountEqual(actual_hwid_db, 'sboard data')

  def testLoadHWIDDBByName_InvalidName(self):
    self._mock_git_fs.ReadFile.side_effect = {
        'projects.yaml': _SERVER_BOARDS_DATA,
        'SBOARD': b'sboard data'
    }.__getitem__

    with self.assertRaises(ValueError):
      self._hwid_repo.LoadHWIDDBByName('NO_SUCH_BOARD')

  def testLoadHWIDDBByName_ValidNameButDbNotFound(self):
    self._mock_git_fs.ReadFile.side_effect = {
        'projects.yaml': _SERVER_BOARDS_DATA,
    }.__getitem__

    with self.assertRaises(hwid_repo.HWIDRepoError):
      self._hwid_repo.LoadHWIDDBByName('SBOARD')


if __name__ == '__main__':
  unittest.main()
