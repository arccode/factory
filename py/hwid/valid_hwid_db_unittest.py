#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Test to verify that all v3 HWID databases are valid.

The test may be invoked in two ways:
  1. As a unittest in platform/factory repo. In this case all the v3 boards
     listed in boards.yaml are checked. The test loads and tests database from
     each corresponding branch.
  2. As a pre-submit check in platform/chromeos-hwid repo. In this case only the
     changed files in each commit are tested.

For each board that the test finds, the test checks that:
  1. The board is listed in boards.yaml.
  2. The checksum of the database is correct (if applicable).
  3. If a test file is found, run through each test case listed in the test
     file. Normally a test file contains a list of encoding and decoding tests.
"""


import logging
import os
import re
import subprocess
import unittest
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.hwdb.hwid_tool import ProbeResults  # pylint: disable=E0611
from cros.factory.hwid import common, database
from cros.factory.hwid import hwid_utils
from cros.factory.rule import Context
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

    # Always read boards.yaml from ToT as all boards are required to have an
    # entry in it.
    boards_info = yaml.load(process_utils.CheckOutput(
        ['git', 'show', 'remotes/cros-internal/master:boards.yaml'],
        cwd=hwid_dir))
    # Get the list of modified HWID databases.
    files = os.environ.get('PRESUBMIT_FILES')
    if files:
      files = files.splitlines()
    else:
      # If PRESUBMIT_FILES is not found, defaults to test all v3 boards in
      # boards.yaml.
      files = [b['path'] for b in boards_info.itervalues() if b['version'] == 3]

    for f in files:
      board_name = os.path.basename(f)
      if board_name not in boards_info:
        if self.V3_HWID_DATABASE_PATH_REGEXP.search(f):
          self.fail(msg='HWID database %r is not listed in boards.yaml' % f)
        continue

      board_info = boards_info[board_name]

      if board_info['version'] != 3:
        # Only check v3 HWID database in this test.
        continue

      # If PRESUBMIT_COMMIT is empty, defaults to checking all the HWID database
      # in their corresponding branches.
      commit = (os.environ.get('PRESUBMIT_COMMIT') or
                'cros-internal/%s' % boards_info[board_name]['branch'])
      db_path = board_info['path']
      test_path = os.path.join(os.path.dirname(db_path), 'testdata',
                               board_name + '_test.yaml')

      logging.info('Checking %s: %s:%s', board_name, commit, db_path)
      try:
        db_raw = process_utils.CheckOutput(
                ['git', 'show', '%s:%s' % (commit, db_path)],
                cwd=hwid_dir, ignore_stderr=True)
      except subprocess.CalledProcessError as e:
        if e.returncode == 128:
          logging.info('Database %s is removed. Skip test for %s.',
                       db_path, board_name)
          continue
        raise

      # Load databases and verify checksum. For old factory branches that do not
      # have database checksum, the checksum verification will be skipped.
      db_yaml = yaml.load(db_raw)
      if 'checksum' in db_yaml:
        with file_utils.UnopenedTemporaryFile() as temp_db:
          with open(temp_db, 'w') as f:
            f.write(db_raw)
          expected_checksum = database.Database.Checksum(temp_db)
      else:
        expected_checksum = None

      if expected_checksum is None:
        logging.warn(
            'Database %s:%s does not have checksum field. Will skip checksum '
            'verification.', commit, db_path)
      db = database.Database.LoadData(
          db_yaml, expected_checksum=expected_checksum,
          strict=bool(expected_checksum))

      try:
        test_samples = yaml.load_all(process_utils.CheckOutput(
                ['git', 'show', '%s:%s' % (commit, test_path)],
                cwd=hwid_dir, ignore_stderr=True))
      except subprocess.CalledProcessError as e:
        if e.returncode == 128:
          logging.info('Cannot find %s. Skip encoding / decoding test for %s.',
                       test_path, board_name)
          continue
        raise

      for sample in test_samples:
        if sample['test'] == 'encode':
          self.TestEncode(db, sample)
        elif sample['test'] == 'decode':
          self.TestDecode(db, sample)
        else:
          raise ValueError('Invalid test type: %r' % sample['test'])

  def TestEncode(self, db, sample_dict):
    # Set up test variables.
    error = None
    binary_string = None
    encoded_string = None

    if 'error' in sample_dict:
      error = sample_dict['error'].strip()
      description = sample_dict['description']
      logging.info('Testing encoding with %s. Expecting error: %r',
                   description, error)
    else:
      binary_string = sample_dict['binary_string']
      encoded_string = sample_dict['encoded_string']
      logging.info('Testing encoding of BOM to %r', encoded_string)

    # Pull in probe results (including VPD data) from the given file
    # rather than probing the current system.
    probe_results = ProbeResults.Decode(yaml.dump(sample_dict['probe_results']))
    vpd = {'ro': {}, 'rw': {}}
    for k, v in probe_results.found_volatile_values.items():
      # Use items(), not iteritems(), since we will be modifying the dict in the
      # loop.
      match = re.match('^vpd\.(ro|rw)\.(\w+)$', k)
      if match:
        del probe_results.found_volatile_values[k]
        vpd[match.group(1)][match.group(2)] = v
    device_info = sample_dict.get('device_info')
    rma_mode = sample_dict.get('rma_mode')

    def _Encode():
      hwid = hwid_utils.GenerateHWID(db, probe_results, device_info, vpd,
                                     rma_mode)
      # Test all rules.
      db.rules.EvaluateRules(Context(hwid=hwid, vpd=vpd,
                                     device_info=device_info))
      return hwid

    if error:
      self.assertRaisesRegexp(Exception, re.compile(error, re.S), _Encode)
    else:
      hwid = _Encode()
      self.assertEquals(binary_string, hwid.binary_string,
                        common.CompareBinaryString(hwid.database, binary_string,
                                                   hwid.binary_string))
      self.assertEquals(encoded_string, hwid.encoded_string)

  def TestDecode(self, db, sample_dict):
    error = None
    binary_string = None
    encoded_fields = None

    encoded_string = sample_dict['encoded_string']
    if 'error' in sample_dict:
      error = sample_dict['error'].strip()
      description = sample_dict['description']
      logging.info('Testing decoding of %r with %s. Expecting error: %r',
                   encoded_string, description, error)
    else:
      binary_string = sample_dict['binary_string']
      encoded_fields = sample_dict['encoded_fields']
      logging.info('Testing decoding of %r to BOM', encoded_string)

    def _Decode():
      # Test decoding.
      return hwid_utils.DecodeHWID(db, encoded_string)

    if error:
      self.assertRaisesRegexp(Exception, re.compile(error, re.S), _Decode)
    else:
      hwid = _Decode()
      self.assertEquals(binary_string, hwid.binary_string)
      self.assertEquals(encoded_fields, hwid.bom.encoded_fields)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
