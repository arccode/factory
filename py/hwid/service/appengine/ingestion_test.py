#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for ingestion."""

import os
import unittest

import mock
import webapp2  # pylint: disable=import-error
import webtest  # pylint: disable=import-error

# pylint: disable=import-error
import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.hwid.service.appengine import filesystem_adapter
from cros.factory.hwid.service.appengine import ingestion

SERVER_BOARDS_YAML = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'testdata/boards_server.yaml')
SERVER_BOARDS_DATA = open(SERVER_BOARDS_YAML, 'r').read()


@mock.patch.object(
    ingestion.RefreshHandler, 'UpdatePayloadsAndSync', mock.Mock())
class IngestionTest(unittest.TestCase):

  def setUp(self):
    app = webapp2.WSGIApplication([('/ingestion/upload',
                                    ingestion.DevUploadHandler),
                                   ('/ingestion/refresh',
                                    ingestion.RefreshHandler)])
    self.testapp = webtest.TestApp(app)

    CONFIG.hwid_manager = mock.Mock()
    CONFIG.hwid_filesystem = mock.Mock()

  def testRefresh(self):
    def MockReadFile(*args):
      if args[0] == '/staging/boards.yaml':
        return SERVER_BOARDS_DATA
      else:
        return 'Test Data'

    CONFIG.hwid_filesystem.ReadFile = mock.Mock(side_effect=MockReadFile)

    response = self.testapp.post('/ingestion/refresh')

    self.assertEqual(response.status_int, 200)
    CONFIG.hwid_manager.UpdateBoards.assert_has_calls([
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
        })
    ])

  def testRefreshWithoutBoardsInfo(self):
    CONFIG.hwid_filesystem.ReadFile = mock.Mock(
        side_effect=filesystem_adapter.FileSystemAdaptorException)

    with self.assertRaises(webtest.app.AppError):
      self.testapp.post('/ingestion/refresh')

  def testUpload(self):
    CONFIG.hwid_filesystem.ListFiles.return_value = ['foo']

    response = self.testapp.post('/ingestion/upload', {'path': 'foo'},
                                 upload_files=[('data', 'bar', 'bar')])

    self.assertEqual(response.status_int, 200)
    CONFIG.hwid_filesystem.WriteFile.assert_called_with('foo', 'bar')

  def testUploadInvalid(self):
    with self.assertRaises(webtest.app.AppError):
      self.testapp.post('/ingestion/upload', {},
                        upload_files=[('data', 'bar', 'bar')])

    with self.assertRaises(webtest.app.AppError):
      self.testapp.post('/ingestion/upload', {'path': 'foo'},
                        upload_files=[])

    with self.assertRaises(webtest.app.AppError):
      self.testapp.post('/ingestion/upload', {'path': 'foo', 'data': 'bar'})


if __name__ == '__main__':
  unittest.main()
