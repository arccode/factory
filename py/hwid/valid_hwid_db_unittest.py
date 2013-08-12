#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Test to verify that all v3 HWID databases are valid."""


import logging
import os
import re
import unittest2
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.gooftool import Gooftool
from cros.factory.hwdb.hwid_tool import ProbeResults  # pylint: disable=E0611
from cros.factory.hwid import common
from cros.factory.rule import Context


class ValidHWIDDBsTest(unittest2.TestCase):
  def runTest(self):
    hwid_dir = os.path.join(
        os.environ['CROS_WORKON_SRCROOT'],
        'src', 'platform', 'chromeos-hwid')

    board_to_test = []
    for board_name, board in yaml.load(
        open(os.path.join(hwid_dir, 'boards.yaml'))).iteritems():
      if board['version'] == 3:
        db_path = os.path.join(hwid_dir, board['path'])
        test_path = os.path.join(os.path.dirname(db_path), 'testdata',
                                 board_name + '_test.yaml')
        board_to_test.append((board_name, db_path, test_path))

    for board_info in board_to_test:
      board_name, db_path, test_path = board_info
      logging.info('Checking %s: %s', board_name, db_path)
      if not os.path.exists(test_path):
        logging.info('Cannot find %s. Skip test for %s.', test_path, board_name)
        continue
      with open(test_path) as f:
        test_samples = yaml.load_all(f.read())
      for sample in test_samples:
        if sample['test'] == 'encode':
          self.TestEncode(board_name, db_path, sample)
        elif sample['test'] == 'decode':
          self.TestDecode(board_name, db_path, sample)
        else:
          raise ValueError('Invalid test type: %r' % sample['test'])

  def TestEncode(self, board_name, db_path, sample_dict):
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

    def _Encode():
      gt = Gooftool(hwid_version=3, board=board_name,
                    hwdb_path=os.path.dirname(db_path))
      # Test HWID Generation.
      hwid = gt.GenerateHwidV3(probe_results=probe_results,
                               device_info=device_info,
                               probed_ro_vpd=vpd['ro'],
                               probed_rw_vpd=vpd['rw'])
      # Test all rules.
      gt.db.rules.EvaluateRules(Context(hwid=hwid, vpd=vpd,
                                        device_info=device_info))
      return hwid

    if error:
      self.assertRaisesRegexp(Exception, re.compile(error, re.S),
                              _Encode)
    else:
      hwid = _Encode()
      self.assertEquals(binary_string, hwid.binary_string,
                        common.CompareBinaryString(hwid.database, binary_string,
                                                   hwid.binary_string))
      self.assertEquals(encoded_string, hwid.encoded_string)

  def TestDecode(self, board_name, db_path, sample_dict):
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
      gt = Gooftool(hwid_version=3, board=board_name,
                    hwdb_path=os.path.dirname(db_path))
      # Test HWID decoding.
      return gt.DecodeHwidV3(encoded_string)

    if error:
      self.assertRaisesRegexp(Exception, re.compile(error, re.S),
                              _Decode)
    else:
      hwid = _Decode()
      self.assertEquals(binary_string, hwid.binary_string)
      self.assertEquals(encoded_fields, hwid.bom.encoded_fields)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest2.main()
