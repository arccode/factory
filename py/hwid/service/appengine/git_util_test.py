#!/usr/bin/env python
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for cros.factory.hwid.service.appengine.git_util"""

import datetime
import unittest

# pylint: disable=import-error, no-name-in-module
import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.appengine import git_util


# pylint: disable=protected-access
class GitUtilTest(unittest.TestCase):

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


if __name__ == '__main__':
  unittest.main()
