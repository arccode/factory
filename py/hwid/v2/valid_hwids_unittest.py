#!/usr/bin/env python3
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test to verify that all v2 HWID databases are valid.

Since all HWID v2 projects have reached EOL, the factory toolkit on ToT is
no longer support them and we don't expect any future HWID changes either.
The test is simply just make sure the recorded HWID databases stay not
changed.
"""

import os
import unittest
import hashlib

from cros.factory.hwid.v3 import hwid_utils
from cros.factory.hwid.v3 import yaml_wrapper as yaml
from cros.factory.test.env import paths
from cros.factory.utils import json_utils
from cros.factory.utils import process_utils


_FREEZED_DB_CHECKSUM_FILE = os.path.join(
    paths.FACTORY_DIR, '..', 'factory-private', 'hwid_v2_testdata',
    'freezed_db_checksums.json')


class ValidHWIDsTest(unittest.TestCase):
  def runTest(self):
    hwid_dir = hwid_utils.GetHWIDRepoPath()
    # Developer from chromiumos community can't access the HWID repository.
    if not os.path.isdir(hwid_dir):
      return

    freezed_hwid_db_checksums = json_utils.LoadFile(_FREEZED_DB_CHECKSUM_FILE)

    target_commit = os.environ.get('PRESUBMIT_COMMIT') or 'cros-internal/main'

    projects_info = yaml.load(process_utils.CheckOutput(
        ['git', 'show', '%s:projects.yaml' % target_commit], cwd=hwid_dir))

    # Check the checksum of *all* HWID v2 databases.
    for proj_info in projects_info.values():
      if proj_info['version'] != 2:
        continue

      self.assertEqual(proj_info['branch'], 'main')

      expected_checksum = freezed_hwid_db_checksums.pop(proj_info['path'])
      raw_hwid_db = process_utils.CheckOutput(
          ['git', 'show', '%s:%s' % (target_commit, proj_info['path'])],
          cwd=hwid_dir, ignore_stderr=True)
      checksum = hashlib.sha1(raw_hwid_db.encode('utf-8')).hexdigest()
      self.assertEqual(checksum, expected_checksum)

    self.assertFalse(freezed_hwid_db_checksums)


if __name__ == '__main__':
  unittest.main()
