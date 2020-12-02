#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for ingestion."""

import collections
import os
import unittest
from unittest import mock

# pylint: disable=import-error, wrong-import-order, no-name-in-module
from google.cloud import ndb
import yaml
# pylint: enable=import-error, wrong-import-order, no-name-in-module

from cros.factory.hwid.service.appengine import hwid_manager
from cros.factory.hwid.service.appengine import ingestion
# pylint: disable=import-error, no-name-in-module
from cros.factory.hwid.service.appengine.proto import ingestion_pb2
# pylint: enable=import-error, no-name-in-module
from cros.factory.hwid.v3 import filesystem_adapter
from cros.factory.probe_info_service.app_engine import protorpc_utils
from cros.factory.utils import file_utils


SERVER_BOARDS_YAML = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'testdata/boards_server.yaml')
SERVER_BOARDS_DATA = file_utils.ReadFile(SERVER_BOARDS_YAML, encoding=None)


class IngestionTest(unittest.TestCase):

  def setUp(self):
    patcher = mock.patch('__main__.ingestion.CONFIG.hwid_filesystem')
    self.patch_hwid_filesystem = patcher.start()
    self.addCleanup(patcher.stop)

    patcher = mock.patch('__main__.ingestion.CONFIG.hwid_manager')
    self.patch_hwid_manager = patcher.start()
    self.addCleanup(patcher.stop)

    patcher = mock.patch('__main__.ingestion._GetCredentials',
                         return_value=('', ''))
    patcher.start()
    self.addCleanup(patcher.stop)

    self.git_fs = mock.Mock()
    patcher = mock.patch('__main__.ingestion._GetHwidRepoFilesystemAdapter',
                         return_value=self.git_fs)
    patcher.start()
    self.addCleanup(patcher.stop)

    self.service = ingestion.ProtoRPCService()

  def testRefresh(self):
    def MockReadFile(*args):
      if args[0] == 'projects.yaml':
        return SERVER_BOARDS_DATA
      return b'Test Data'

    self.git_fs.ReadFile = MockReadFile

    request = ingestion_pb2.IngestHwidDbRequest()
    response = self.service.IngestHwidDb(request)

    self.assertEqual(
        response, ingestion_pb2.IngestHwidDbResponse(msg='Skip for local env'))
    self.patch_hwid_manager.UpdateBoards.assert_has_calls([
        mock.call(
            self.git_fs, {
                'COOLCBOARD': {
                    'path': 'COOLCBOARD',
                    'board': 'COOLCBOARD',
                    'version': 3
                },
                'SBOARD': {
                    'path': 'SBOARD',
                    'board': 'SBOARD',
                    'version': 3
                },
                'KBOARD': {
                    'path': 'KBOARD',
                    'board': 'KBOARD',
                    'version': 2
                },
                'KBOARD.old': {
                    'path': 'KBOARD.old',
                    'board': 'KBOARD',
                    'version': 2
                },
                'BETTERCBOARD': {
                    'path': 'BETTERCBOARD',
                    'board': 'BETTERCBOARD',
                    'version': 3
                }
            }, delete_missing=True)
    ])

  def testRefreshWithoutBoardsInfo(self):
    self.git_fs.ReadFile = mock.Mock(
        side_effect=filesystem_adapter.FileSystemAdapterException)

    request = ingestion_pb2.IngestHwidDbRequest()
    with self.assertRaises(protorpc_utils.ProtoRPCException) as ex:
      self.service.IngestHwidDb(request)
    self.assertEqual(ex.exception.detail, 'Missing file during refresh.')


class AVLNameTest(unittest.TestCase):

  NAME_PATTERN_FOLDER = 'name_pattern'
  NAME_MAPPING_FOLDER = 'avl_name_mapping'

  def setUp(self):
    patcher = mock.patch('__main__.ingestion.CONFIG.hwid_filesystem')
    self.patch_hwid_filesystem = patcher.start()
    self.addCleanup(patcher.stop)

    patcher = mock.patch('__main__.ingestion._GetAuthCookie')
    patcher.start()
    self.addCleanup(patcher.stop)

    self.git_fs = mock.Mock()
    patcher = mock.patch('__main__.ingestion._GetHwidRepoFilesystemAdapter',
                         return_value=self.git_fs)
    patcher.start()
    self.addCleanup(patcher.stop)

    self.service = ingestion.ProtoRPCService()

    self.init_mapping_data = {
        'category1': {
            2: "name1",
            4: "name2",
            6: "name3",
        },
        'category2': {
            1: "name3",
            2: "name4",
            3: "name5",
        }
    }
    self.update_mapping_data = {
        'category2': {
            2: "name4",
            3: "name6",
            4: "name8",
        },
        'category3': {
            5: "name5",
            7: "name7",
            9: "name9",
        }
    }

    self.mock_init_mapping = {
        category + '.yaml': yaml.dump(mapping, default_flow_style=False)
        for category, mapping in self.init_mapping_data.items()
    }

    self.mock_update_mapping = {
        category + '.yaml': yaml.dump(mapping, default_flow_style=False)
        for category, mapping in self.update_mapping_data.items()
    }

  def testSyncNamePattern(self):
    mock_name_pattern = {
        'category1.yaml': (b'- "pattern1\n"'
                           b'- "pattern2\n"'
                           b'- "pattern3\n"'),
        'category2.yaml': (b'- "pattern4\n"'
                           b'- "pattern5\n"'
                           b'- "pattern6\n"')
    }

    def PatchGitListFiles(folder):
      if folder == self.NAME_PATTERN_FOLDER:
        return list(mock_name_pattern)
      return []

    def PatchGitReadFile(path):
      folder, filename = os.path.split(path)
      self.assertEqual(folder, self.NAME_PATTERN_FOLDER)
      return mock_name_pattern[filename]

    self.git_fs.ListFiles = PatchGitListFiles
    self.git_fs.ReadFile = PatchGitReadFile

    self.patch_hwid_filesystem.ListFiles.return_value = []

    request = ingestion_pb2.SyncNamePatternRequest()
    response = self.service.SyncNamePattern(request)
    self.assertEqual(response, ingestion_pb2.SyncNamePatternResponse())

    self.patch_hwid_filesystem.ListFiles.assert_has_calls(
        [mock.call(self.NAME_PATTERN_FOLDER)])

    expected_call_count = 0
    for filename, content in mock_name_pattern.items():
      path = os.path.join('name_pattern', filename)
      expected_call_count += 1
      self.patch_hwid_filesystem.WriteFile.assert_any_call(path, content)
    self.assertEqual(self.patch_hwid_filesystem.WriteFile.call_count,
                     expected_call_count)

  def testSyncNameMapping(self):
    """Perform two round sync and check the consistency."""

    def PatchGitListFilesWrapper(mapping):

      def func(folder):
        if folder == self.NAME_MAPPING_FOLDER:
          return list(mapping)
        return []

      return func

    def PatchGitReadFileWrapper(mapping):

      def func(path):
        folder, filename = os.path.split(path)
        self.assertEqual(folder, self.NAME_MAPPING_FOLDER)
        return mapping[filename]

      return func

    # Init mapping
    self.git_fs.ListFiles = PatchGitListFilesWrapper(self.mock_init_mapping)
    self.git_fs.ReadFile = PatchGitReadFileWrapper(self.mock_init_mapping)

    request = ingestion_pb2.SyncNamePatternRequest()
    response = self.service.SyncNamePattern(request)
    self.assertEqual(response, ingestion_pb2.SyncNamePatternResponse())

    mapping_in_datastore = collections.defaultdict(dict)
    with ndb.Client().context():
      for entry in hwid_manager.AVLNameMapping.query():
        self.assertIn(entry.category, self.init_mapping_data)
        mapping_in_datastore[entry.category][entry.component_id] = entry.name
    self.assertDictEqual(mapping_in_datastore, self.init_mapping_data)

    # Update mapping
    self.git_fs.ListFiles = PatchGitListFilesWrapper(self.mock_update_mapping)
    self.git_fs.ReadFile = PatchGitReadFileWrapper(self.mock_update_mapping)

    request = ingestion_pb2.SyncNamePatternRequest()
    response = self.service.SyncNamePattern(request)
    self.assertEqual(response, ingestion_pb2.SyncNamePatternResponse())

    mapping_in_datastore = collections.defaultdict(dict)
    with ndb.Client().context():
      for entry in hwid_manager.AVLNameMapping.query():
        self.assertIn(entry.category, self.update_mapping_data)
        mapping_in_datastore[entry.category][entry.component_id] = entry.name
    self.assertDictEqual(mapping_in_datastore, self.update_mapping_data)


if __name__ == '__main__':
  unittest.main()
