#!/usr/bin/python -u
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""The unittest for the service_manager."""


import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.docker_env import service_manager
from cros.factory.utils import process_utils


class RepositoryTest(unittest.TestCase):
  def setUp(self):
    # pylint:disable=protected-access
    self.repos = service_manager._MANAGED_REPOS

  def testRepositoriesExist(self):
    for repo_url, _ in self.repos:
      process_utils.LogAndCheckCall(['git', 'ls-remote', '-h', repo_url])


if __name__ == '__main__':
  unittest.main()
