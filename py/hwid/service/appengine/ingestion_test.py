#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for ingestion."""

import http
import io
import os
import unittest

# pylint: disable=import-error, wrong-import-order
import flask
import mock
# pylint: enable=import-error, wrong-import-order

from cros.factory.hwid.service.appengine import app
from cros.factory.hwid.v3 import filesystem_adapter
from cros.factory.utils import file_utils


SERVER_BOARDS_YAML = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'testdata/boards_server.yaml')
SERVER_BOARDS_DATA = file_utils.ReadFile(SERVER_BOARDS_YAML, encoding=None)


class IngestionTest(unittest.TestCase):

  def setUp(self):
    hwid_service = app.hwid_service
    self.app = hwid_service.test_client()
    hwid_service.test_request_context().push()

    patcher = mock.patch('__main__.app.ingestion.CONFIG.hwid_filesystem')
    self.patch_hwid_filesystem = patcher.start()
    self.addCleanup(patcher.stop)

    patcher = mock.patch('__main__.app.ingestion.CONFIG.hwid_manager')
    self.patch_hwid_manager = patcher.start()
    self.addCleanup(patcher.stop)

  def testRefresh(self):
    def MockReadFile(*args):
      if args[0] == 'staging/boards.yaml':
        return SERVER_BOARDS_DATA
      return b'Test Data'

    self.patch_hwid_filesystem.ReadFile = mock.Mock(
        side_effect=MockReadFile)

    response = self.app.post(flask.url_for('refresh'))

    self.assertEqual(response.status_code, http.HTTPStatus.OK)
    self.patch_hwid_manager.UpdateBoards.assert_has_calls([
        mock.call({
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
    self.patch_hwid_filesystem.ReadFile = mock.Mock(
        side_effect=filesystem_adapter.FileSystemAdapterException)

    response = self.app.post(flask.url_for('refresh'))
    self.assertEqual(response.data, b'Missing file during refresh.')
    self.assertEqual(response.status_code,
                     http.HTTPStatus.INTERNAL_SERVER_ERROR)

  def testUpload(self):
    self.patch_hwid_filesystem.ListFiles.return_value = ['foo']

    response = self.app.post(
        flask.url_for('upload'), content_type='multipart/form-data', data={
            'data': (io.BytesIO(b'bar'), 'bar'),
            'path': 'foo'})

    self.assertEqual(response.status_code, http.HTTPStatus.OK)
    self.patch_hwid_filesystem.WriteFile.assert_called_with('foo', b'bar')

  def testUploadInvalid(self):
    response = self.app.post(
        flask.url_for('upload'), content_type='multipart/form-data', data={
            'data': (io.BytesIO(b'bar'), 'bar')})
    self.assertEqual(response.status_code, http.HTTPStatus.BAD_REQUEST)

    response = self.app.post(
        flask.url_for('upload'), content_type='multipart/form-data', data={
            'path': 'foo'})
    self.assertEqual(response.status_code, http.HTTPStatus.BAD_REQUEST)

    response = self.app.post(
        flask.url_for('upload'), content_type='multipart/form-data', data={
            'path': 'foo',
            'data': b'bar'})
    self.assertEqual(response.status_code, http.HTTPStatus.BAD_REQUEST)


if __name__ == '__main__':
  unittest.main()
