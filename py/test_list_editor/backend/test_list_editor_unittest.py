#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import tempfile
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.test_list_editor.backend import common
from cros.factory.test_list_editor.backend import test_list_editor


_APO = test_list_editor._AddPrivateOverlay  # pylint: disable=protected-access

_FAKE_REPO_SCHEMA = {
    '.repo': {},
    'src': {
        'aaa/bbb': {},
        'private-overlays/overlay-asdf-private': {
            '.git': {},
            'ccc/ddd': {},
            'chromeos-base/factory-board/files/py/test/test_lists': {}
        }
    }
}


def _CreateDirectories(path, schema):
  for k, v in schema.iteritems():
    new_path = os.path.join(path, k)
    os.makedirs(new_path)
    _CreateDirectories(new_path, v)


class AddPrivateOverlayTest(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.tmp_dir = tempfile.mkdtemp()
    _CreateDirectories(cls.tmp_dir, _FAKE_REPO_SCHEMA)
    common.SCRIPT_DIR = os.path.join(cls.tmp_dir, 'src/aaa/bbb')
    fake_private_overlay = os.path.join(
        cls.tmp_dir, 'src/private-overlays/overlay-asdf-private')
    cls.fake_private_somewhere = os.path.join(fake_private_overlay, 'ccc/ddd')
    cls.expected_asdf = [(
        'asdf',
        os.path.join(
            fake_private_overlay, 'chromeos-base/factory-board/files'))]

  @classmethod
  def tearDownClass(cls):
    os.chdir('/')
    shutil.rmtree(cls.tmp_dir)

  def setUp(self):
    os.chdir('/')

  def testNoPrivateOverlay(self):
    _APO(None, None)

  @mock.patch('cros.factory.utils.sys_utils.InCrOSDevice')
  def testSpecifiedBoardInDUT(self, m_in_cros_dev):
    m_in_cros_dev.return_value = True
    self.assertRaises(ValueError, _APO, None, 'asdf')

  def testSpecificBoardExist(self):
    dirs = []
    _APO(dirs, 'asdf')
    self.assertEqual(dirs, self.expected_asdf)

  def testSpecificBoardNotExist(self):
    self.assertRaises(RuntimeError, _APO, None, 'fdsa')

  def testInPrivateOverlay(self):
    os.chdir(self.fake_private_somewhere)
    dirs = []
    _APO(dirs, None)
    self.assertEqual(dirs, self.expected_asdf)


if __name__ == '__main__':
  unittest.main()
