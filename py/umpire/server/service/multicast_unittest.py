#!/usr/bin/env python3
#
# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest
from unittest import mock

from cros.factory.umpire.server.service import multicast
from cros.factory.utils import json_utils


DEFAULT_PORT = 8080
TESTDATA_DIR = os.path.join(os.path.dirname(__file__), 'testdata')


def TestData(filename):
  return os.path.join(TESTDATA_DIR, filename)


class GenerateConfigTest(unittest.TestCase):

  def setUp(self):
    self.payload = json_utils.LoadFile(
        os.path.join(TESTDATA_DIR, 'example_payload.json'))

  def testEnableAll(self):
    _SERVICE_CONFIG_ENABLE_ALL = {
        'mgroup': '224.1.2.3',
        'server_ip': '192.168.1.1',
        'required_components': {
            "release_image": True,
            "test_image": True,
            "toolkit": True
        }
    }

    generated_config = multicast.MulticastService.GenerateConfig(
        _SERVICE_CONFIG_ENABLE_ALL, self.payload, DEFAULT_PORT)
    expected_config = json_utils.LoadFile(
        TestData('mcast_config_enable_all.json'))
    self.assertEqual(generated_config, expected_config)

  def testEnableToolkit(self):
    _SERVICE_CONFIG_ENABLE_TOOLKIT = {
        'mgroup': '224.1.2.3',
        'server_ip': '192.168.1.1',
        'required_components': {
            "release_image": False,
            "test_image": False,
            "toolkit": True
        }
    }
    generated_config = multicast.MulticastService.GenerateConfig(
        _SERVICE_CONFIG_ENABLE_TOOLKIT, self.payload, DEFAULT_PORT)
    expected_config = json_utils.LoadFile(
        TestData('mcast_config_enable_toolkit.json'))
    self.assertEqual(generated_config, expected_config)

  def testDefaultValues(self):
    # Enable one component here to test default mgroup value.
    _SERVICE_CONFIG_DEFAULT_VALUES = {
        'required_components': {
            "test_image": True
        }
    }
    generated_config = multicast.MulticastService.GenerateConfig(
        _SERVICE_CONFIG_DEFAULT_VALUES, self.payload, DEFAULT_PORT)
    expected_config = json_utils.LoadFile(
        TestData('mcast_config_default_values.json'))
    self.assertEqual(generated_config, expected_config)

  def testNoServerIp(self):
    """Test when `server_ip` is assigned, but `mgroup` is not given."""
    _SERVICE_CONFIG_NO_SERVER_IP = {
        'mgroup': '224.1.2.3',
        'required_components': {
            "test_image": True
        }
    }
    generated_config = multicast.MulticastService.GenerateConfig(
        _SERVICE_CONFIG_NO_SERVER_IP, self.payload, DEFAULT_PORT)
    expected_config = json_utils.LoadFile(
        TestData('mcast_config_no_server_ip.json'))
    self.assertEqual(generated_config, expected_config)

  def testAutoAssignMgroup(self):
    """Test auto assigning `mgroup` from server_ip."""
    _SERVICE_CONFIG_AUTO_ASSIGN_MGROUP = {
        'server_ip': '192.168.12.34',
        'required_components': {
            "test_image": True
        }
    }
    generated_config = multicast.MulticastService.GenerateConfig(
        _SERVICE_CONFIG_AUTO_ASSIGN_MGROUP, self.payload, DEFAULT_PORT)
    expected_config = json_utils.LoadFile(
        TestData('mcast_config_auto_assign_mgroup.json'))
    self.assertEqual(generated_config, expected_config)

  def testBadMgroup(self):
    _SERVICE_CONFIG_BAD_MGROUP = {
        'mgroup': '123456',
        'required_components': {
            "test_image": True
        }
    }
    with self.assertRaises(AssertionError):
      multicast.MulticastService.GenerateConfig(_SERVICE_CONFIG_BAD_MGROUP,
                                                self.payload, DEFAULT_PORT)

  def testAutoAssignMgroupWithBadServerIp(self):
    _SERVICE_CONFIG_BAD_SERVER_IP = {
        'server_ip': '123456',
        'required_components': {
            "test_image": True
        }
    }
    # Raised by the `.group()` call from a None object returned by `re.search`.
    with self.assertRaises(AttributeError):
      multicast.MulticastService.GenerateConfig(_SERVICE_CONFIG_BAD_SERVER_IP,
                                                self.payload, DEFAULT_PORT)


class MulticastServiceTest(unittest.TestCase):
  _DUMMY_MCAST_CONFIG = {
      'dummy_key': 'dummy_value'
  }
  _FAKE_UMPIRE_CONFIG = {
      'services': {
          'multicast': {}
      }
  }
  _FAKE_UMPIRE_BASE_DIR = 'umpire_base_dir'
  _FAKE_MCAST_RESOURCE_NAME = 'multicast.32d4f1f4ba53b174acc8aa0a68fb53bd.json'

  @mock.patch('cros.factory.utils.file_utils.ForceSymlink')
  @mock.patch(multicast.__name__ + '.MulticastService.GenerateConfig')
  def testCreateProcesses(self, mock_generate_config, mock_force_sym_link):
    mock_generate_config.return_value = self._DUMMY_MCAST_CONFIG

    mock_env = mock.MagicMock()
    mock_env.base_dir = self._FAKE_UMPIRE_BASE_DIR
    mock_env.AddConfigFromBlob.return_value = self._FAKE_MCAST_RESOURCE_NAME

    ret = multicast.MulticastService().CreateProcesses(self._FAKE_UMPIRE_CONFIG,
                                                       mock_env)

    self.assertEqual(ret, [])
    mock_env.AddConfigFromBlob.assert_called_once_with(
        json_utils.DumpStr(self._DUMMY_MCAST_CONFIG, pretty=True),
        'multicast_config')
    mock_force_sym_link.assert_called_once_with(
        os.path.join('resources', self._FAKE_MCAST_RESOURCE_NAME),
        os.path.join(self._FAKE_UMPIRE_BASE_DIR, 'multicast_config.json'))


if __name__ == '__main__':
  unittest.main()
