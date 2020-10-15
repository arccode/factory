#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest
from unittest import mock

from cros.factory.test.utils import model_sku_utils


class TestModelSKUUtils(unittest.TestCase):
  """Unit tests for model_sku_utils."""

  @staticmethod
  def _SetProjectConfigMock(listdir_mock, load_config_mock):
    """Mock a project config database."""
    listdir_mock.return_value = [
        'program1_project1_model_sku.json', 'program1_project2_model_sku.json',
        'program2_project3_model_sku.json', 'program2_project4_model_sku.json'
    ]
    load_config_mock.side_effect = [{
        'model': {
            'design1': {
                'has_laser': True
            },
            'design2': {
                'has_laser': False
            }
        },
        'product_sku': {
            'Fakeproduct': {
                '6': {
                    'fw_config': 121
                }
            }
        }
    }, {
        'model': {
            'design3': {
                'has_laser': True
            },
            'design4': {
                'has_laser': False
            }
        },
        'product_sku': {
            'Fakeproduct': {
                '7': {
                    'fw_config': 122
                }
            }
        }
    }, {
        'model': {
            'design5': {
                'has_laser': True
            },
            'design6': {
                'has_laser': False
            }
        },
        'product_sku': {
            'fake,cool,rev0': {
                '8': {
                    'fw_config': 123
                }
            }
        }
    }, {
        'model': {
            'design7': {
                'has_laser': True
            },
            'design8': {
                'has_laser': False
            }
        },
        'product_sku': {
            'fake,hao,rev123': {
                '9': {
                    'fw_config': 124
                }
            }
        }
    }]

  @staticmethod
  def _SetCrosConfigMock(cros_config_mock, sku_id, model):
    """Mock cros_config."""
    # Constructor returns itself
    cros_config_mock.return_value = cros_config_mock
    cros_config_mock.GetSkuID.return_value = sku_id
    cros_config_mock.GetModelName.return_value = model

  @mock.patch('os.listdir')
  @mock.patch('cros.factory.gooftool.cros_config.CrosConfig')
  @mock.patch('cros.factory.utils.config_utils.LoadConfig')
  @mock.patch('cros.factory.utils.sys_interface.SystemInterface')
  def testGetDesignConfigX86(self, sys_mock, load_config_mock, cros_config_mock,
                             listdir_mock):
    """Test GetDesignConfig on X86 devices."""
    sys_mock.ReadFile.return_value = 'Fakeproduct'
    self._SetCrosConfigMock(cros_config_mock, '6', 'design1')
    self._SetProjectConfigMock(listdir_mock, load_config_mock)
    design_config = model_sku_utils.GetDesignConfig(sys_mock)
    self.assertEqual(design_config['fw_config'], 121)
    self.assertEqual(design_config['program'], 'program1')
    self.assertEqual(design_config['project'], 'project1')
    self.assertEqual(design_config['has_laser'], True)

    sys_mock.ReadFile.return_value = 'Fakeproduct'
    self._SetCrosConfigMock(cros_config_mock, '7', 'design4')
    self._SetProjectConfigMock(listdir_mock, load_config_mock)
    design_config = model_sku_utils.GetDesignConfig(sys_mock)
    self.assertEqual(design_config['fw_config'], 122)
    self.assertEqual(design_config['program'], 'program1')
    self.assertEqual(design_config['project'], 'project2')
    self.assertEqual(design_config['has_laser'], False)

    sys_mock.ReadFile.return_value = 'Virtualproduct'
    self._SetCrosConfigMock(cros_config_mock, '7', 'design0')
    self._SetProjectConfigMock(listdir_mock, load_config_mock)
    design_config = model_sku_utils.GetDesignConfig(sys_mock)
    self.assertEqual(design_config, {})

  @mock.patch('os.listdir')
  @mock.patch('cros.factory.gooftool.cros_config.CrosConfig')
  @mock.patch('cros.factory.utils.config_utils.LoadConfig')
  @mock.patch('cros.factory.utils.sys_interface.SystemInterface')
  def testGetDesignConfigARM(self, sys_mock, load_config_mock, cros_config_mock,
                             listdir_mock):
    """Test GetDesignConfig on ARM devices."""
    sys_mock.ReadFile.side_effect = [
        # Read from PRODUCT_NAME_PATH and fail.
        Exception(),
        # Read from DEVICE_TREE_COMPATIBLE_PATH.
        'fake,hao,rev123\0fake,cool,rev0'
    ]
    self._SetCrosConfigMock(cros_config_mock, '8', 'design5')
    self._SetProjectConfigMock(listdir_mock, load_config_mock)
    design_config = model_sku_utils.GetDesignConfig(sys_mock)
    self.assertEqual(design_config['fw_config'], 123)
    self.assertEqual(design_config['program'], 'program2')
    self.assertEqual(design_config['project'], 'project3')
    self.assertEqual(design_config['has_laser'], True)

    sys_mock.ReadFile.side_effect = [
        # Read from PRODUCT_NAME_PATH and fail.
        Exception(),
        # Read from DEVICE_TREE_COMPATIBLE_PATH.
        'fake,hao,rev123\0fake,cool,rev0'
    ]
    self._SetCrosConfigMock(cros_config_mock, '9', 'design8')
    self._SetProjectConfigMock(listdir_mock, load_config_mock)
    design_config = model_sku_utils.GetDesignConfig(sys_mock)
    self.assertEqual(design_config['fw_config'], 124)
    self.assertEqual(design_config['program'], 'program2')
    self.assertEqual(design_config['project'], 'project4')
    self.assertEqual(design_config['has_laser'], False)

    sys_mock.ReadFile.side_effect = [
        # Read from PRODUCT_NAME_PATH and fail.
        Exception(),
        # Read from DEVICE_TREE_COMPATIBLE_PATH.
        'fake,bad,rev123\0fake,boo,rev0'
    ]
    self._SetCrosConfigMock(cros_config_mock, '9', 'design9')
    self._SetProjectConfigMock(listdir_mock, load_config_mock)
    design_config = model_sku_utils.GetDesignConfig(sys_mock)
    self.assertEqual(design_config, {})


if __name__ == '__main__':
  unittest.main()
