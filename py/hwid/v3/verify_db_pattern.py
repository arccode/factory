#!/usr/bin/env python3
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Verifies that new commits do not alter existing encoding patterns.

This test may be invoked in multiple ways:
  1. Execute manually. In this case all the v3 projects listed in projects.yaml
     are checked. The test loads and compares new and old databases from HEAD
     and HEAD~1, respectively, in each corresponding branch of each project.
  2. As a pre-submit check in platform/chromeos-hwid repo. In this case only the
     changed HWID databases in each commit are tested.
  3. VerifyParsedDatabasePattern may be called directly by the HWID Server.
"""

import argparse
import logging
import multiprocessing
import os
import subprocess
import sys
import traceback
import unittest

from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import filesystem_adapter
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.hwid.v3 import name_pattern_adapter
from cros.factory.hwid.v3 import validator_context
from cros.factory.hwid.v3 import yaml_wrapper as yaml
from cros.factory.utils import process_utils
from cros.factory.utils.schema import SchemaException


def _TestDatabase(targs):
  db_path, projects_info, commit, hwid_dir = targs
  project_name = os.path.basename(db_path)
  if project_name not in projects_info:
    logging.info('Removing %s in this commit, skipped', project_name)
    return None
  try:
    title = '%s %s:%s' % (project_name, commit, db_path)
    logging.info('Checking %s', title)
    if projects_info[project_name]['branch'] != 'master':
      raise Exception('Project %r is not on master' % (
          projects_info[project_name]['branch'],))
    HWIDDBsPatternTest.VerifyDatabasePattern(hwid_dir, commit, db_path)
    return None
  except Exception:
    return (title, traceback.format_exception(*sys.exc_info()))


class HWIDDBsPatternTest(unittest.TestCase):
  """Unit test for HWID database."""

  def __init__(self, project=None, commit=None):
    super(HWIDDBsPatternTest, self).__init__()
    self.project = project
    self.commit = commit

  def runTest(self):
    hwid_dir = hwid_utils.GetHWIDRepoPath()
    if not os.path.exists(hwid_dir):
      logging.info(
          'ValidHWIDDBsTest: ignored, no %s in source tree.', hwid_dir)
      return

    # Always read projects.yaml from ToT as all projects are required to have an
    # entry in it.
    target_commit = (self.commit or os.environ.get('PRESUBMIT_COMMIT') or
                     'cros-internal/master')
    projects_info = yaml.load(process_utils.CheckOutput(
        ['git', 'show', '%s:projects.yaml' % target_commit], cwd=hwid_dir))


    if self.project:
      if self.project not in projects_info:
        self.fail('Invalid project %r' % self.project)
      test_args = [('v3/%s' % self.project, projects_info, target_commit,
                    hwid_dir)]
    else:
      files = os.environ.get('PRESUBMIT_FILES')
      if files:
        test_args = [(f.partition('/platform/chromeos-hwid/')[-1],
                      projects_info, target_commit, hwid_dir)
                     for f in files.splitlines()]
      else:
        # If PRESUBMIT_FILES is not found, defaults to test all v3 projects in
        # projects.yaml.
        test_args = [(b['path'], projects_info, target_commit, hwid_dir) for b
                     in projects_info.values() if b['version'] == 3]

    pool = multiprocessing.Pool()
    exception_list = pool.map(_TestDatabase, test_args)
    exception_list = list(filter(None, exception_list))

    if exception_list:
      error_msg = []
      for title, err_msg_lines in exception_list:
        error_msg.append('Error occurs in %s\n' % title +
                         ''.join('  ' + l for l in err_msg_lines))
      raise Exception('\n'.join(error_msg))

  @staticmethod
  def GetOldNewDB(hwid_dir, commit, db_path):
    """Get old and new DB.

    Get the DB in commit and the previous version (None not applicable).

    Args:
      hwid_dir: Path of the base directory of HWID databases.
      commit: The commit hash value of the newest version of HWID database.
      db_path: Path of the HWID database to be verified.
    Returns:
      tuple (old_db, new_db), old_db could be None if the commit is the init
      commit for the project.
    """
    # A compatible version of HWID database can be loaded successfully.
    new_db = Database.LoadData(
        process_utils.CheckOutput(['git', 'show', '%s:%s' % (commit, db_path)],
                                  cwd=hwid_dir, ignore_stderr=True))

    try:
      raw_old_db = process_utils.CheckOutput(
          ['git', 'show', '%s~1:%s' % (commit, db_path)], cwd=hwid_dir,
          ignore_stderr=True)
    except subprocess.CalledProcessError as e:
      if e.returncode != 128:
        raise e
      logging.info('Adding new HWID database %s; skip pattern check',
                   os.path.basename(db_path))
      return None, new_db

    try:
      old_db = Database.LoadData(raw_old_db)
    except (SchemaException, common.HWIDException) as e:
      logging.warning('The previous version of HWID database %s is an '
                      'incompatible version (exception: %r), ignore the '
                      'pattern check', db_path, e)
      return None, new_db
    return old_db, new_db

  @staticmethod
  def VerifyDatabasePattern(hwid_dir, commit, db_path):
    """Verify the specific HWID database.

    This method obtains the old_db and new_db, creates a context about
    filesystem used in name_pattern_adapter.NamePatternAdapter, and passes to
    ValidateChange static method.

    Args:
      hwid_dir: Path of the base directory of HWID databases.
      commit: The commit hash value of the newest version of HWID database.
      db_path: Path of the HWID database to be verified.
    """
    old_db, new_db = HWIDDBsPatternTest.GetOldNewDB(hwid_dir, commit, db_path)
    ctx = validator_context.ValidatorContext(
        filesystem_adapter=filesystem_adapter.LocalFileSystemAdapter(hwid_dir))
    HWIDDBsPatternTest.ValidateChange(old_db, new_db, ctx)

  @staticmethod
  def VerifyNewCreatedDatabasePattern(new_db):
    if not new_db.can_encode:
      raise common.HWIDException(
          'The new HWID database should not use legacy pattern.  Please use '
          '"hwid build-database" to prevent from generating legacy pattern.')

    region_field_legacy_info = new_db.region_field_legacy_info
    if not region_field_legacy_info or any(region_field_legacy_info.values()):
      raise common.HWIDException(
          'Legacy region field is forbidden in any new HWID database.')

  @staticmethod
  def VerifyParsedDatabasePattern(old_db, new_db):
    # If the old database follows the new pattern rule, so does the new
    # database.
    if old_db.can_encode and not new_db.can_encode:
      raise common.HWIDException(
          'The new HWID database should not use legacy pattern. '
          'Please use "hwid update-database" to prevent from generating '
          'legacy pattern.')

    # Make sure all the encoded fields in the existing patterns are not changed.
    for image_id in old_db.image_ids:
      old_bit_mapping = old_db.GetBitMapping(image_id=image_id)
      new_bit_mapping = new_db.GetBitMapping(image_id=image_id)
      for index, (element_old, element_new) in enumerate(zip(old_bit_mapping,
                                                             new_bit_mapping)):
        if element_new != element_old:
          raise common.HWIDException(
              'Bit pattern mismatch found at bit %d (encoded field=%r). '
              'If you are trying to append new bit(s), be sure to create a new '
              'bit pattern field instead of simply incrementing the last '
              'field' % (index, element_old[0]))

    old_region_field_legacy_info = old_db.region_field_legacy_info
    new_region_field_legacy_info = new_db.region_field_legacy_info
    for field_name, is_legacy_style in new_region_field_legacy_info.items():
      orig_is_legacy_style = old_region_field_legacy_info.get(field_name)
      if orig_is_legacy_style is None:
        if is_legacy_style:
          raise common.HWIDException(
              'New region field should be constructed by new style yaml tag.')
      else:
        if orig_is_legacy_style != is_legacy_style:
          raise common.HWIDException(
              'Style of existing region field should remain unchanged.')

  @staticmethod
  def ValidateChange(old_db, new_db, ctx):
    """Validate changes between old_db and new_db.

    This method checks 3 things:
      1. Verify whether the newest version of the HWID database is compatible
          with the current version of HWID module.
      2. If the previous version of the HWID database exists and is compatible
          with the current version of HWID module, verify whether all the
          encoded fields in the previous version of HWID database are not
          changed.
      3. Check if component names matches the predefined rule by
          name_pattern_adapter.

    Args:
      old_db: db before the change.
      new_db: db after the change.
      ctx: validator_context.ValidatorContext instance which contains the
           name_pattern information.
    """

    if old_db is None:
      HWIDDBsPatternTest.VerifyNewCreatedDatabasePattern(new_db)
    else:
      HWIDDBsPatternTest.VerifyParsedDatabasePattern(old_db, new_db)
    HWIDDBsPatternTest.ValidateComponentChange(old_db, new_db, ctx)

  @staticmethod
  def ValidateComponentChange(old_db, db, ctx):
    """Check if modified (created) component names are valid.

    Args:
      old_db: db before the change.
      new_db: db after the change.
      ctx: validator_context.ValidatorContext instance which contains the
           name_pattern information.
    """

    def FindModifiedComponentNamesWithIdx(old_db, db, comp_cls):
      name_idx = {}
      for idx, tag in enumerate(db.GetComponents(comp_cls), 1):
        name_idx[tag] = idx

      if old_db is not None:
        for tag in old_db.GetComponents(comp_cls):
          name_idx.pop(tag, None)

      return name_idx

    adapter = name_pattern_adapter.NamePatternAdapter(ctx.filesystem_adapter)
    rename_component = {}
    for comp_cls in db.GetActiveComponentClasses():
      name_pattern = adapter.GetNamePatterns(comp_cls)
      if name_pattern:
        modified_names = FindModifiedComponentNamesWithIdx(old_db, db, comp_cls)
        for tag, idx in modified_names.items():
          if not name_pattern.Matches(tag):
            raise common.HWIDException(
                '%r does not match any available %s pattern' % (tag, comp_cls))
          sp = tag.split('#', 1)
          if len(sp) == 2:
            expected_component_name = '%s#%d' % (sp[0], idx)
            if tag != expected_component_name:
              rename_component[tag] = expected_component_name

    if rename_component:
      raise common.HWIDException(
          'Invalid component names with sequence number, please modify them as '
          'follows:\n' +
          '\n'.join('- ' + k + ' -> ' + v for k, v in rename_component.items()))


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('--commit', help='the commit to test')
  parser.add_argument('--project', type=str, default=None,
                      help='name of the project to test')
  args = parser.parse_args()
  logging.basicConfig(level=logging.INFO)

  runner = unittest.TextTestRunner()
  test = HWIDDBsPatternTest(project=args.project, commit=args.commit)
  result = runner.run(test)
  sys.exit(0 if result.wasSuccessful() else 1)
