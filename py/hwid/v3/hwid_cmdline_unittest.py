#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import os
import unittest

import mock
import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3.common import HWIDException
from cros.factory.hwid.v3 import hwid_cmdline
from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


class FakeOutput(object):
  def __init__(self):
    self.data = ''

  def __call__(self, msg):
    self.data += msg + '\n'


class TestCaseBaseWithFakeOutput(unittest.TestCase):
  def setUp(self):
    self.orig_output = hwid_cmdline.Output
    hwid_cmdline.Output = FakeOutput()

  def tearDown(self):
    hwid_cmdline.Output = self.orig_output


class OutputObjectTest(TestCaseBaseWithFakeOutput):
  def testYamlFormat(self):
    hwid_cmdline.OutputObject(mock.MagicMock(json_output=False),
                              {'aaa': ['bbb', 'ccc'], 'xxx': 3})
    self.assertEquals(yaml.load(hwid_cmdline.Output.data),
                      {'aaa': ['bbb', 'ccc'], 'xxx': 3})

  def testJsonFormat(self):
    hwid_cmdline.OutputObject(mock.MagicMock(json_output=True),
                              {'aaa': ['bbb', 'ccc'], 'xxx': 3})
    self.assertEquals(json.loads(hwid_cmdline.Output.data),
                      {'aaa': ['bbb', 'ccc'], 'xxx': 3})


class TestCaseBaseWithMockedOutputObject(unittest.TestCase):
  def setUp(self):
    self.orig_output_object = hwid_cmdline.OutputObject
    hwid_cmdline.OutputObject = mock.MagicMock()

  def tearDown(self):
    hwid_cmdline.OutputObject = self.orig_output_object


class ObtainAllDeviceDataTest(unittest.TestCase):
  @mock.patch('cros.factory.hwid.v3.yaml_wrapper.dump')
  @mock.patch('cros.factory.hwid.v3.hwid_utils.GetVPDData')
  @mock.patch('cros.factory.hwid.v3.hwid_utils.GetDeviceInfo')
  @mock.patch('cros.factory.hwid.v3.hwid_utils.GetProbedResults')
  def testNormal(self, get_probed_results_mock, get_device_info_mock,
                 get_vpd_data_mock, unused_dump_mock):
    options = mock.MagicMock(run_vpd=False)
    ret = hwid_cmdline.ObtainAllDeviceData(options)

    # The function should call below functions to get the proper device data.
    get_probed_results_mock.assert_called_once_with(
        infile=options.probed_results_file)
    get_vpd_data_mock.assert_called_once_with(
        run_vpd=options.run_vpd, infile=options.vpd_data_file)
    get_device_info_mock.assert_called_once_with(
        infile=options.device_info_file)

    self.assertEquals(type_utils.Obj(probed_results=ret.probed_results,
                                     vpd=ret.vpd,
                                     device_info=ret.device_info),
                      ret)


class BuildDatabaseWrapperTest(unittest.TestCase):
  @mock.patch('cros.factory.hwid.v3.builder.DatabaseBuilder')
  @mock.patch('cros.factory.hwid.v3.hwid_cmdline.ObtainAllDeviceData')
  def testNormal(self, obtain_all_device_data_mock, build_database_mock):
    with file_utils.TempDirectory() as path:
      options = mock.MagicMock()
      options.hwid_db_path = path
      options.add_default_comp = ['a', 'b']
      options.add_null_comp = ['c', 'd']

      hwid_cmdline.BuildDatabaseWrapper(options)

      # Constructor.
      build_database_mock.assert_called_with(project=options.project,
                                             image_name=options.image_id)
      instance = build_database_mock.return_value

      # Update default/null components.
      instance.AddDefaultComponent.assert_has_calls(
          [mock.call('a'), mock.call('b')], any_order=True)
      instance.AddNullComponent.assert_has_calls(
          [mock.call('c'), mock.call('d')], any_order=True)

      # Update by the probed results.
      instance.UpdateByProbedResults.assert_called_with(
          obtain_all_device_data_mock.return_value.probed_results,
          obtain_all_device_data_mock.return_value.device_info,
          obtain_all_device_data_mock.return_value.vpd,
          image_name=options.image_id)


class UpdateDatabaseWrapperTest(unittest.TestCase):
  @mock.patch('cros.factory.hwid.v3.builder.DatabaseBuilder')
  @mock.patch('cros.factory.hwid.v3.hwid_cmdline.ObtainAllDeviceData')
  def testNormal(self, obtain_all_device_data_mock, build_database_mock):
    with file_utils.TempDirectory() as path:
      options = mock.MagicMock()
      options.hwid_db_path = path
      options.add_default_comp = ['a', 'b']
      options.add_null_comp = ['c', 'd']
      options.project = 'proj'

      hwid_cmdline.UpdateDatabaseWrapper(options)

      # Constructor.
      build_database_mock.assert_called_with(
          database_path=os.path.join(path, 'PROJ'))
      instance = build_database_mock.return_value

      # Update default/null components.
      instance.AddDefaultComponent.assert_has_calls(
          [mock.call('a'), mock.call('b')], any_order=True)
      instance.AddNullComponent.assert_has_calls(
          [mock.call('c'), mock.call('d')], any_order=True)

      # Update by the probed results.
      instance.UpdateByProbedResults.assert_called_with(
          obtain_all_device_data_mock.return_value.probed_results,
          obtain_all_device_data_mock.return_value.device_info,
          obtain_all_device_data_mock.return_value.vpd,
          image_name=options.image_id)


class GenerateHWIDWrapperTest(TestCaseBaseWithMockedOutputObject):
  @mock.patch('cros.factory.hwid.v3.hwid_utils.GenerateHWID')
  @mock.patch('cros.factory.hwid.v3.hwid_cmdline.ObtainAllDeviceData')
  def testNormal(self, obtain_all_device_data_mock, generate_hwid_mock):
    options = mock.MagicMock()
    hwid_cmdline.GenerateHWIDWrapper(options)

    device_data = obtain_all_device_data_mock.return_value
    generate_hwid_mock.assert_called_once_with(
        options.database, device_data.probed_results,
        device_data.device_info, device_data.vpd,
        options.rma_mode,
        allow_mismatched_components=options.allow_mismatched_components,
        use_name_match=options.use_name_match)

    identity = generate_hwid_mock.return_value
    hwid_cmdline.OutputObject.assert_called_once_with(
        options,
        {'encoded_string': identity.encoded_string,
         'binary_string': identity.binary_string,
         'database_checksum': options.database.checksum})


class DecodeHWIDWrapperTest(TestCaseBaseWithMockedOutputObject):
  @mock.patch('cros.factory.hwid.v3.hwid_utils.DecodeHWID',
              return_value=(mock.MagicMock(), mock.MagicMock()))
  def testNormal(self, decode_hwid_mock):
    options = mock.MagicMock()
    hwid_cmdline.DecodeHWIDWrapper(options)

    decode_hwid_mock.assert_called_once_with(options.database, options.hwid)
    identity, bom = decode_hwid_mock.return_value

    hwid_cmdline.OutputObject.assert_called_once_with(
        options,
        {'project': identity.project,
         'binary_string': identity.binary_string,
         'image_id': bom.image_id,
         'components': bom.components})


class VerifyHWIDWrapperTest(TestCaseBaseWithFakeOutput):
  @mock.patch('cros.factory.hwid.v3.hwid_utils.VerifyHWID')
  @mock.patch('cros.factory.hwid.v3.hwid_cmdline.ObtainAllDeviceData')
  def testNormal(self, obtain_all_device_data_mock, verify_hwid_mock):
    options = mock.MagicMock()
    hwid_cmdline.VerifyHWIDWrapper(options)

    device_data = obtain_all_device_data_mock.return_value

    verify_hwid_mock.assert_called_once_with(
        options.database, options.hwid,
        device_data.probed_results,
        device_data.device_info, device_data.vpd,
        options.rma_mode, current_phase=options.phase,
        allow_mismatched_components=options.allow_mismatched_components)

  @mock.patch('cros.factory.hwid.v3.hwid_utils.VerifyHWID',
              side_effect=HWIDException('verify fail'))
  @mock.patch('cros.factory.hwid.v3.hwid_cmdline.ObtainAllDeviceData')
  def testVerifyFailed(
      self, unused_obtain_all_device_data_mock, unused_verify_hwid_mock):
    self.assertRaises(HWIDException, hwid_cmdline.VerifyHWIDWrapper,
                      mock.MagicMock())


class ListComponentsWrapperTest(TestCaseBaseWithMockedOutputObject):
  @mock.patch('cros.factory.hwid.v3.hwid_utils.ListComponents')
  def testNormal(self, list_components_mock):
    options = mock.MagicMock()
    hwid_cmdline.ListComponentsWrapper(options)

    list_components_mock.assert_called_once_with(options.database,
                                                 options.comp_class)
    hwid_cmdline.OutputObject.assert_called_once_with(
        options, list_components_mock.return_value)


class EnumerateHWIDWrapperTest(TestCaseBaseWithFakeOutput):
  @mock.patch('cros.factory.hwid.v3.hwid_utils.EnumerateHWID',
              return_value={'HWID1': 'bbb', 'HWID2': 'aaa'})
  def testDefault(self, unused_enumerate_hwid_mock):
    hwid_cmdline.EnumerateHWIDWrapper(mock.MagicMock(comp=None, no_bom=False))

    self.assertEquals(hwid_cmdline.Output.data, 'HWID1: bbb\nHWID2: aaa\n')

  @mock.patch('cros.factory.hwid.v3.hwid_utils.EnumerateHWID', return_value={})
  def testComp(self, enumerate_hwid_mock):
    options = mock.MagicMock(comp=['aaa=bbb', 'ccc=ddd,eee'])
    hwid_cmdline.EnumerateHWIDWrapper(options)

    enumerate_hwid_mock.assert_called_once_with(
        options.database,
        image_id=options.database.GetImageIdByName.return_value,
        status=options.status,
        comps={'aaa': ['bbb'], 'ccc': ['ddd', 'eee']})

  @mock.patch('cros.factory.hwid.v3.hwid_utils.EnumerateHWID',
              return_value={'HWID1': 'bbb', 'HWID2': 'aaa'})
  def testOutputWithoutBOM(self, unused_enumerate_hwid_mock):
    hwid_cmdline.EnumerateHWIDWrapper(mock.MagicMock(no_bom=True))

    self.assertEquals(hwid_cmdline.Output.data, 'HWID1\nHWID2\n')


if __name__ == '__main__':
  unittest.main()
