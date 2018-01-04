#!/usr/bin/env python
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Test to verify that all v3 HWID databases are valid.

The test may be invoked in two ways:
  1. As a unittest in platform/factory repo. In this case all the v3 projects
     listed in projects.yaml are checked. The test loads and tests database from
     each corresponding branch.
  2. As a pre-submit check in platform/chromeos-hwid repo. In this case only the
     changed files in each commit are tested.

For each project that the test finds, the test checks that:
  1. The project is listed in projects.yaml.
  2. The checksum of the database is correct (if applicable).
  3. If a test file is found, run through each test case listed in the test
     file. Normally a test file contains a list of encoding and decoding tests.
"""


import logging
import os
import re
import subprocess
import sys
import traceback
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import yaml_wrapper as yaml
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


class ValidHWIDDBsTest(unittest.TestCase):
  """Unit test for HWID database."""
  V3_HWID_DATABASE_PATH_REGEXP = re.compile('v3/[A-Z]+$')

  def runTest(self):
    hwid_dir = os.path.join(
        os.environ['CROS_WORKON_SRCROOT'],
        'src', 'platform', 'chromeos-hwid')
    if not os.path.exists(hwid_dir):
      print 'ValidHWIDDBsTest: ignored, no %s in source tree.' % hwid_dir
      return

    # Always read projects.yaml from ToT as all projects are required to have an
    # entry in it.
    projects_info = yaml.load(process_utils.CheckOutput(
        ['git', 'show', 'remotes/cros-internal/master:projects.yaml'],
        cwd=hwid_dir))
    # Get the list of modified HWID databases.
    files = os.environ.get('PRESUBMIT_FILES')
    if files:
      files = files.splitlines()
    else:
      # If PRESUBMIT_FILES is not found, defaults to test all v3 projects in
      # projects.yaml.
      files = [b['path'] for b in projects_info.itervalues()
               if b['version'] == 3]

    exception_list = []
    for f in files:
      project_name = os.path.basename(f)
      if project_name not in projects_info:
        if self.V3_HWID_DATABASE_PATH_REGEXP.search(f):
          self.fail(msg='HWID database %r is not listed in projects.yaml' % f)
        continue

      project_info = projects_info[project_name]

      if project_info['version'] != 3:
        # Only check v3 HWID database in this test.
        continue

      # If PRESUBMIT_COMMIT is empty, defaults to checking all the HWID database
      # in their corresponding branches.
      commit = (os.environ.get('PRESUBMIT_COMMIT') or
                'cros-internal/%s' % projects_info[project_name]['branch'])
      db_path = project_info['path']
      title = '%s %s:%s' % (project_name, commit, db_path)
      logging.info('Checking %s', title)

      try:
        db_raw = process_utils.CheckOutput(
            ['git', 'show', '%s:%s' % (commit, db_path)],
            cwd=hwid_dir, ignore_stderr=True)
      except subprocess.CalledProcessError as e:
        if e.returncode == 128:
          logging.info('Database %s is removed. Skip test for %s.',
                       db_path, project_name)
          continue
        exception_list.append((title, sys.exc_info()))
        continue

      # Load databases and verify checksum. For old factory branches that do not
      # have database checksum, the checksum verification will be skipped.
      try:
        db_yaml = yaml.load(db_raw)
        if 'checksum' in db_yaml:
          with file_utils.UnopenedTemporaryFile() as temp_db:
            with open(temp_db, 'w') as f:
              f.write(db_raw)
            expected_checksum = Database.Checksum(temp_db)
        else:
          expected_checksum = None

        if expected_checksum is None:
          logging.warn(
              'Database %s:%s does not have checksum field. Will skip checksum '
              'verification.', commit, db_path)
        unused_db = Database.LoadData(
            db_yaml, expected_checksum=expected_checksum,
            strict=bool(expected_checksum))
      except Exception:
        logging.error('%s: Load database failed.', project_name)
        exception_list.append((title, sys.exc_info()))
        continue

    if exception_list:
      error_msg = []
      for title, info in exception_list:
        error_msg.append('Error occurs in %s\n' % title +
                         ''.join(traceback.format_exception(*info)))
      raise Exception('\n'.join(error_msg))


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
