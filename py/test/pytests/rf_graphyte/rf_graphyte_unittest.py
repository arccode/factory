#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for rf_graphyte factory test."""

import json
import os
import shutil
import tempfile
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.test.pytests.rf_graphyte import rf_graphyte


class PatchSSHLinkConfigUnittest(unittest.TestCase):
  """Unit tests for rf_graphyte PatchSSHLinkConfig."""

  # pylint: disable=protected-access
  def setUp(self):
    self.mock_ip = 'MOCK_SSH_IP'
    self.config_folder = tempfile.mkdtemp()
    self.test = rf_graphyte.RFGraphyteTest()
    self.test.config_file_path = os.path.join(self.config_folder,
                                              'graphyte_config.json')
    self.test._dut = mock.MagicMock()
    self.test._dut.link.host = self.mock_ip

  def tearDown(self):
    if os.path.isdir(self.config_folder):
      shutil.rmtree(self.config_folder)

  def testPatchConfig(self):
    mock_config = {
        'dut': 'sample.dummy_dut',
        'dut_config_file': 'sample_dummy_dut.json'}
    expected_config = {
        'dut': 'sample.dummy_dut',
        'dut_config_file': 'sample_dummy_dut.json',
        'dut_config': {
            'link_options': {
                'host': self.mock_ip}}}
    with open(self.test.config_file_path, 'w') as f:
      json.dump(mock_config, f)
    self.test.PatchSSHLinkConfig()
    with open(self.test.config_file_path, 'r') as f:
      patched_config = json.load(f)
    self.assertEquals(expected_config, patched_config)


  def testOverrideExistedConfig(self):
    mock_config = {
        'dut': 'sample.dummy_dut',
        'dut_config_file': 'sample_dummy_dut.json',
        'dut_config': {
            'link_options': {
                'host': '192.168.0.1'}}}
    expected_config = {
        'dut': 'sample.dummy_dut',
        'dut_config_file': 'sample_dummy_dut.json',
        'dut_config': {
            'link_options': {
                'host': self.mock_ip}}}
    with open(self.test.config_file_path, 'w') as f:
      json.dump(mock_config, f)
    self.test.PatchSSHLinkConfig()
    with open(self.test.config_file_path, 'r') as f:
      patched_config = json.load(f)
    self.assertEquals(expected_config, patched_config)


if __name__ == '__main__':
  unittest.main()
