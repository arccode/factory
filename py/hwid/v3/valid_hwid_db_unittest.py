#!/usr/bin/env python3
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Test to verify that all v3 HWID databases are valid.

The test may be invoked in two ways:
  1. As a unittest in platform/factory repo. In this case all the v3 projects
     listed in projects.yaml are checked. The test loads and tests database from
     ToT.
  2. As a pre-submit check in platform/chromeos-hwid repo. In this case only the
     changed files in each commit are tested.

For each project that the test finds, the test checks that:
  1. The project is listed in projects.yaml.
  2. The checksum of the database is correct (if applicable).
  3. If a test file is found, run through each test case listed in the test
     file. Normally a test file contains a list of encoding and decoding tests.
"""


import logging
import multiprocessing
import os
import re
import sys
import traceback
import unittest

from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import contents_analyzer
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.hwid.v3 import yaml_wrapper as yaml
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


BLOCKLIST_PROJECT = []


def _CheckProject(args):
  """Check if HWID database of a V3 HWID is valid.

  Args:
    args: A tuple of (project_name, project_info, hwid_dir).

  Returns:
    None if the database is valid, else a tuple of (title, error message).
  """
  project_name, db_path, project_info, hwid_dir = args
  presubmit_commit = os.environ.get('PRESUBMIT_COMMIT')
  commit = presubmit_commit or 'cros-internal/main'

  title = '%s %s:%s' % (project_name, commit, db_path)
  logging.info('Checking %s', title)

  try:
    if project_name in BLOCKLIST_PROJECT:
      logging.warning('%s in the blocklist, skip.', project_name)
      return None

    if project_info is None:
      # Missing project info in projects.yaml is only expected to happen when
      # running a presubmit check for a commit that removes the HWID database.
      if presubmit_commit:
        returncode = process_utils.Spawn(
            ['git', 'show', '%s:%s' % (presubmit_commit, db_path)],
            cwd=hwid_dir, call=True, ignore_stdin=True, ignore_stdout=True,
            ignore_stderr=True).returncode
        if returncode == 128:
          logging.info('Database %s is removed.  Skip test for %s.', db_path,
                       project_name)
          return None

      raise ValueError(
          'missing metadata in projects.yaml for the project %r' % project_name)

    assert project_info['branch'] == 'main'

    db_raw = process_utils.CheckOutput(
        ['git', 'show', '%s:%s' % (commit, db_path)], cwd=hwid_dir,
        ignore_stderr=True)

    # Load databases and verify checksum. For old factory branches that do not
    # have database checksum, the checksum verification will be skipped.
    if any([re.match('^checksum: ', line) for line in db_raw.split('\n')]):
      with file_utils.UnopenedTemporaryFile() as temp_db:
        file_utils.WriteFile(temp_db, db_raw)
        expected_checksum = Database.Checksum(temp_db)
    else:
      expected_checksum = None
      logging.warning(
          'Database %s:%s does not have checksum field. Will skip checksum '
          'verification.', commit, db_path)
    contents_analyzer_inst = contents_analyzer.ContentsAnalyzer(
        db_raw, expected_checksum, None)
    report = contents_analyzer_inst.ValidateIntegrity()
    for msg in report.warnings:
      logging.warning(msg)
    if report.errors:
      raise ValueError(f'Validation failed: {report.errors}')
    return None
  except Exception:
    return (title, traceback.format_exception(*sys.exc_info()))


class ValidHWIDDBsTest(unittest.TestCase):
  """Unit test for HWID database."""
  V3_HWID_DATABASE_PATH_REGEXP = re.compile('v3/[A-Z0-9]+$')

  def runTest(self):
    hwid_dir = hwid_utils.GetHWIDRepoPath()
    if not os.path.exists(hwid_dir):
      logging.info('ValidHWIDDBsTest: ignored, no %s in source tree.', hwid_dir)
      return

    target_commit = (os.environ.get('PRESUBMIT_COMMIT') or 'cros-internal/main')
    projects_info = yaml.load(process_utils.CheckOutput(
        ['git', 'show', '%s:projects.yaml' % target_commit], cwd=hwid_dir))

    presubmit_files = os.environ.get('PRESUBMIT_FILES')
    if presubmit_files:
      # Only target to the changed HWID v3 databases in pre-submit check.
      target_dbs = []
      for db_path in presubmit_files.splitlines():
        db_path = os.path.relpath(db_path, hwid_dir)
        project_name = os.path.basename(db_path)
        project_info = projects_info.get(project_name)
        if ((project_info and project_info.get('version') == 3) or
            ValidHWIDDBsTest.V3_HWID_DATABASE_PATH_REGEXP.search(db_path)):
          target_dbs.append((project_name, db_path, project_info))
    else:
      # Verify all HWID v3 databases in unittest.
      target_dbs = [(k, v['path'], v) for k, v in projects_info.items()
                    if v['version'] == 3]

    pool = multiprocessing.Pool()
    exception_list = pool.map(
        _CheckProject, [(project_name, db_path, project_info, hwid_dir)
                        for project_name, db_path, project_info in target_dbs])
    exception_list = list(filter(None, exception_list))

    if exception_list:
      error_msg = []
      for title, err_msg_lines in exception_list:
        error_msg.append('Error occurs in %s\n' % title +
                         ''.join('  ' + l for l in err_msg_lines))
      raise Exception('\n'.join(error_msg))


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
