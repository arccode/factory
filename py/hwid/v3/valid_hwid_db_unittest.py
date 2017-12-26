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


import copy
import logging
import os
import re
import subprocess
import sys
import traceback
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.hwid.v3 import base32
from cros.factory.hwid.v3 import base8192
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.hwid.v3.rule import Context
from cros.factory.hwid.v3 import yaml_wrapper as yaml
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


def _MayConvertLegacyProbedResults(probed_results):
  vpd = {'ro': {}, 'rw': {}}

  if 'found_probe_value_map' not in probed_results:
    return probed_results, vpd

  new_probe_results = copy.deepcopy(probed_results['found_probe_value_map'])
  new_probe_results.update(
      copy.deepcopy(probed_results.get('found_volatile_values', {})))

  for comp_cls in new_probe_results.keys():
    if isinstance(new_probe_results[comp_cls], list):
      new_probe_results[comp_cls] = {'generic': new_probe_results[comp_cls]}
    elif isinstance(new_probe_results[comp_cls], dict):
      new_probe_results[comp_cls] = {'generic': [new_probe_results[comp_cls]]}
    else:
      match = re.match(r'^vpd\.(ro|rw)\.(\w+)$', comp_cls)
      if match:
        vpd[match.group(1)][match.group(2)] = new_probe_results[comp_cls]
      del new_probe_results[comp_cls]

  return new_probe_results, vpd


def _CompareBase32BinaryString(db, expected, given):
  def Header(bit_length):
    msg = '\n' + '%12s' % 'Bit offset: ' + ' '.join(
        ['%-5s' % anchor for anchor in xrange(0, bit_length, 5)])
    msg += '\n' + '%12s' % ' ' + ' '.join(
        ['%-5s' % '|' for _ in xrange(0, bit_length, 5)])
    return msg

  def ParseBinaryString(label, string):
    msg = '\n%12s' % (label + ': ') + ' '.join(
        [string[i:i + 5] for i in xrange(0, len(string), 5)])
    msg += '\n%12s' % ' ' + ' '.join(
        ['%5s' % base32.Base32.Encode(string[i:i + 5])
         for i in xrange(0, len(string), 5)])
    return msg

  def BitMap(db):
    bitmap = [(key, value.field, value.bit_offset) for key, value in
              db.pattern.GetBitMapping().iteritems()]
    msg = '\nField to bit mappings:'
    msg += '\n%3s: encoding pattern' % '0'
    msg += '\n' + '\n'.join([
        '%3s: image_id bit %s' % (idx, idx) for idx in xrange(1, 5)])
    msg += '\n' + '\n'.join(['%3s: %s bit %s' % entry for entry in bitmap])
    return msg

  return (Header(len(expected)) +
          ParseBinaryString('Expected', expected) +
          ParseBinaryString('Given', given) +
          BitMap(db))


def _CompareBase8192BinaryString(db, expected, given):
  def Header(bit_length):
    msg = '\n' + '%12s' % 'Bit offset: ' + ' '.join(
        ['%-15s' % anchor for anchor in xrange(0, bit_length, 13)])
    msg += '\n' + '%12s' % ' ' + ' '.join(
        ['%-15s' % '|' for _ in xrange(0, bit_length, 13)])
    return msg

  def ParseBinaryString(label, string):
    msg = '\n%12s' % (label + ': ') + ' '.join(
        ['%-5s %-3s %-5s' % (
            string[i:i + 5], string[i + 5:i + 8], string[i + 8:i + 13])
         for i in xrange(0, len(string), 13)])

    def _SplitString(s):
      results = list(base8192.Base8192.Encode(s))
      if len(results) == 4:
        results = results[0:3]
      if len(results) < 3:
        results.extend([' '] * (3 - len(results)))
      return tuple(results)
    msg += '\n%12s' % ' ' + ' '.join(
        [('%5s %3s %5s' % _SplitString(string[i:i + 13]))
         for i in xrange(0, len(string), 13)])
    return msg

  def BitMap(db):
    bitmap = [(key, value.field, value.bit_offset) for key, value in
              db.pattern.GetBitMapping().iteritems()]
    msg = '\nField to bit mappings:'
    msg += '\n%3s: encoding pattern' % '0'
    msg += '\n' + '\n'.join([
        '%3s: image_id bit %s' % (idx, idx) for idx in xrange(1, 5)])
    msg += '\n' + '\n'.join(['%3s: %s bit %s' % entry for entry in bitmap])
    return msg

  return (Header(len(expected)) +
          ParseBinaryString('Expected', expected) +
          ParseBinaryString('Given', given) +
          BitMap(db))


def _CompareBinaryString(db, expected, given):
  image_id = db.pattern.GetImageIdFromBinaryString(given)
  encoding_scheme = db.pattern.GetPatternByImageId(
      image_id)['encoding_scheme']
  if encoding_scheme == common.HWID.ENCODING_SCHEME.base32:
    return _CompareBase32BinaryString(db, expected, given)
  elif encoding_scheme == common.HWID.ENCODING_SCHEME.base8192:
    return _CompareBase8192BinaryString(db, expected, given)


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
      test_path = os.path.join(os.path.dirname(db_path), 'testdata',
                               project_name + '_test.yaml')
      title = '%s %s:%s' % (project_name, commit, db_path)
      logging.info('Checking %s', title)

      try:
        test_samples = yaml.load_all(process_utils.CheckOutput(
            ['git', 'show', '%s:%s' % (commit, test_path)],
            cwd=hwid_dir, ignore_stderr=True))
      except subprocess.CalledProcessError as e:
        if e.returncode == 128:
          logging.info('Cannot find %s. Skip encoding / decoding test for %s.',
                       test_path, project_name)
          continue
        logging.error('%s: Load testdata failed.', project_name)
        exception_list.append((title, sys.exc_info()))
        continue

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
      except Exception:
        logging.error('%s: Load database failed.', project_name)
        exception_list.append((title, sys.exc_info()))
        continue

      for sample in test_samples:
        try:
          if sample['test'] == 'encode':
            self.TestEncode(db, sample)
          elif sample['test'] == 'decode':
            self.TestDecode(db, sample)
          else:
            raise ValueError('Invalid test type: %r' % sample['test'])
        except Exception as e:
          if 'error' in sample:
            idx = sample['error']
          else:
            idx = sample['encoded_string']
          logging.error('Error occurs in %s: %s', project_name, idx)
          exception_list.append((title, sys.exc_info()))
    if exception_list:
      error_msg = []
      for title, info in exception_list:
        error_msg.append('Error occurs in %s\n' % title +
                         ''.join(traceback.format_exception(*info)))
      raise Exception('\n'.join(error_msg))

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

    probe_results, vpd = _MayConvertLegacyProbedResults(
        sample_dict['probe_results'])

    device_info = sample_dict.get('device_info')
    rma_mode = sample_dict.get('rma_mode')

    def _Encode():
      bom = hwid_utils.GenerateBOMFromProbedResults(db, probe_results)
      hwid = hwid_utils.GenerateHWID(db, bom, device_info,
                                     vpd=vpd, rma_mode=rma_mode)
      # Test all rules.
      db.rules.EvaluateRules(Context(hwid=hwid, vpd=vpd,
                                     device_info=device_info))
      return hwid

    if error:
      self.assertRaisesRegexp(Exception, re.compile(error, re.S), _Encode)
    else:
      hwid = _Encode()
      self.assertEquals(binary_string, hwid.binary_string,
                        _CompareBinaryString(hwid.database, binary_string,
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
      for field_name in db.pattern.GetFieldNames(hwid.bom.image_id):
        self.assertEquals(encoded_fields[field_name],
                          hwid.bom.encoded_fields[field_name])


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
