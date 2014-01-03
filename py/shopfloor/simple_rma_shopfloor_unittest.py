#!/usr/bin/env python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.simple_rma_shopfloor import DecodeHWIDv3Components
from cros.factory.shopfloor.simple_rma_shopfloor import LoadAuxCsvData
from cros.factory.shopfloor.simple_rma_shopfloor import LoadDeviceData
from cros.factory.shopfloor.simple_rma_shopfloor import ShopFloor

_RMA00000000_FILE = 'RMA00000000.yaml'
_RMA11111111_FILE = 'RMA11111111.yaml'
_RMA_CONFIG_BOARD_YAML_1 = """rma_number_yaml_must_exist: False"""
_RMA11111111_YAML_1 = """!DeviceData
gbind_attribute: ''
hwid: DEVICE CADT-QQOP
region: ''
rma_number: RMA11111111
serial_number: ''
ubind_attribute: ''
vpd:
  ro: {initial_locale: en-US, timezone: some_when}
  rw: {attribute1: 1value, attribute2: 2value}
"""
_RMA_CONFIG_BOARD_YAML_2 = """rma_number_yaml_must_exist: True
device_info_fields: [component.antenna, region]
hwid_factory_translation:
  antenna:
    funky_1: cowabunga_man
    funky_2: cowabunga_dude
"""
_RMA11111111_YAML_2 = """!DeviceData
component.antenna: cowabunga_dude
gbind_attribute: ''
hwid: DEVICE CADT-QQOP
region: us
rma_number: RMA11111111
serial_number: ''
ubind_attribute: ''
vpd:
  ro: {initial_locale: en-US, timezone: some_when}
  rw: {attribute1: 1value, attribute2: 2value}
"""
_TEST_HWID = 'DEVICE CADT-QQOP'
_TEST_VPD = {'ro': {'initial_locale': 'en-US', 'timezone': 'some_when'},
             'rw': {'attribute1': '1value', 'attribute2': '2value'}}

class DecodeHWIDv3ComponentsTest(unittest.TestCase):
  def setUp(self):
    self.testdata = os.path.join(os.path.dirname(
        os.path.realpath(__file__)), "testdata")

  def testBasicHWIDv3ComponentDecode(self):
    ret = DecodeHWIDv3Components(_TEST_HWID, self.testdata)
    self.assertEqual(ret['antenna'][0].component_name, 'funky_2')
    self.assertEqual(ret['camera'][0].component_name, 'gnarly_cam')
    self.assertEqual(ret['keyboard'][0].component_name, 'us_clicker')
    self.assertEqual(ret['pcb_vendor'][0].component_name, 'awesome_1')

class LoadAuxCsvDataTest(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.NamedTemporaryFile()

  def tearDown(self):
    self.tmp.close()

  def _WriteValidRows(self):
    print >> self.tmp, "id,a_bool[bool],a_str[str],a_int[int],a_float[float]"
    print >> self.tmp, "1,True,foo,111,.5"
    print >> self.tmp, "2,1,foo,111,.5"
    print >> self.tmp, "3,true,foo,111,.5"
    print >> self.tmp, "4,False,bar,222,1.5"
    print >> self.tmp, "6,false,bar,222,1.5"
    print >> self.tmp, "5,0,bar,222,1.5"

  def _ReadData(self):
    self.tmp.flush()
    return LoadAuxCsvData(self.tmp.name)

  def testValid(self):
    self._WriteValidRows()
    self.assertEqual(
        {'1': {'id': '1',
               'a_bool': True, 'a_str': 'foo', 'a_int': 111, 'a_float': 0.5},
         '2': {'id': '2',
               'a_bool': True, 'a_str': 'foo', 'a_int': 111, 'a_float': 0.5},
         '3': {'id': '3',
               'a_bool': True, 'a_str': 'foo', 'a_int': 111, 'a_float': 0.5},
         '4': {'id': '4',
               'a_bool': False, 'a_str': 'bar', 'a_int': 222, 'a_float': 1.5},
         '5': {'id': '5',
               'a_bool': False, 'a_str': 'bar', 'a_int': 222, 'a_float': 1.5},
         '6': {'id': '6',
               'a_bool': False, 'a_str': 'bar', 'a_int': 222, 'a_float': 1.5}},
        self._ReadData())

  def testDuplicateID(self):
    self._WriteValidRows()
    print >> self.tmp, "1,False,foo,222,.5"
    self.assertRaisesRegexp(ValueError,
                            r"^In \S+:8, duplicate ID '1'$",
                            self._ReadData)

  def testInvalidBoolean(self):
    self._WriteValidRows()
    print >> self.tmp, "1,x,foo,222,.5"
    self.assertRaisesRegexp(ValueError,
                            r"^In \S+:8\.a_bool, 'x' is not a Boolean value$",
                            self._ReadData)

  def testInvalidInt(self):
    self._WriteValidRows()
    print >> self.tmp, "1,True,foo,x,.5"
    self.assertRaisesRegexp(ValueError,
                            r"^In \S+:8\.a_int, invalid literal",
                            self._ReadData)

  def testDuplicateHeader(self):
    print >> self.tmp, "id,a,a"
    self.assertRaisesRegexp(ValueError,
                            r"^In \S+, more than one column named 'a'",
                            self._ReadData)

  def testBadHeader(self):
    print >> self.tmp, "id,a["
    self.assertRaisesRegexp(ValueError,
                            r"^In \S+, header 'a\[' does not match regexp",
                            self._ReadData)

  def testUnknownType(self):
    print >> self.tmp, "id,a[foo]"
    self.assertRaisesRegexp(ValueError,
                            (r"^In \S+, header 'a' has unknown type 'foo' "
                             r"\(should be one of "
                             r"\['bool', 'float', 'int', 'str'\]\)"),
                            self._ReadData)

class LoadDeviceDataTest(unittest.TestCase):
  def setUp(self):
    self.testdata = os.path.join(os.path.dirname(
        os.path.realpath(__file__)), "testdata")

  def testLoadMinimalYAML(self):
    test_yaml = os.path.join(self.testdata, _RMA00000000_FILE)
    device_info_fields = []
    device_dict = LoadDeviceData(test_yaml, device_info_fields)
    self.assertEqual(device_dict['hwid'], _TEST_HWID)
    self.assertEqual(device_dict['registration_code_map']['user'],
                     '<user_code>')
    self.assertEqual(device_dict['registration_code_map']['group'],
                     '<group_code>')
    self.assertEqual(device_dict['vpd']['ro']['initial_locale'],
                     'en-US')
    self.assertEqual(device_dict['vpd']['ro']['initial_timezone'],
                     'America/Los_Angeles')
    self.assertEqual(device_dict['vpd']['ro']['keyboard_layout'],
                     'xkb:us::eng')
    self.assertEqual(device_dict['vpd']['ro']['serial_number'],
                     123456789012345)
    self.assertEqual(device_dict['vpd']['rw'], {})

  def testLoadExpandedYAML(self):
    test_yaml = os.path.join(self.testdata, _RMA00000000_FILE)
    device_info_fields = ['component.camera', 'region', 'serial_number',
                          'gbind_attribute', 'ubind_attribute']
    device_dict = LoadDeviceData(test_yaml, device_info_fields)
    self.assertEqual(device_dict['hwid'], _TEST_HWID)
    self.assertEqual(device_dict['registration_code_map']['user'],
                     '<user_code>')
    self.assertEqual(device_dict['registration_code_map']['group'],
                     '<group_code>')
    self.assertEqual(device_dict['vpd']['ro']['initial_locale'],
                     'en-US')
    self.assertEqual(device_dict['vpd']['ro']['initial_timezone'],
                     'America/Los_Angeles')
    self.assertEqual(device_dict['vpd']['ro']['keyboard_layout'],
                     'xkb:us::eng')
    self.assertEqual(device_dict['vpd']['ro']['serial_number'],
                     123456789012345)
    self.assertEqual(device_dict['vpd']['rw'], {})
    self.assertEqual(device_dict['component.camera'], 'generic_vga')
    self.assertEqual(device_dict['region'], 'us')
    self.assertEqual(device_dict['serial_number'], 123456789012345)
    self.assertEqual(device_dict['gbind_attribute'], '<group_code>')
    self.assertEqual(device_dict['ubind_attribute'], '<user_code>')

class ShopFloorTest(unittest.TestCase):
  def setUp(self):
    self.testdata = os.path.join(os.path.dirname(
        os.path.realpath(__file__)), "testdata")
    self.rma_config = os.path.join(self.testdata, "rma_config_board.yaml")

  def tearDown(self):
    if os.path.isfile(self.rma_config):
      os.remove(self.rma_config)
    if os.path.isfile(os.path.join(self.testdata, _RMA11111111_FILE)):
      os.remove(os.path.join(self.testdata, _RMA11111111_FILE))

  def _WriteRMAConfigYAML(self, file_path, test_config=1):
    self.assertTrue(os.path.exists(os.path.dirname(file_path)))
    if os.path.isfile(file_path):
      os.remove(file_path)
    with open(file_path, 'w') as f:
      if test_config == 1:
        f.write(_RMA_CONFIG_BOARD_YAML_1)
      if test_config == 2:
        f.write(_RMA_CONFIG_BOARD_YAML_2)

  def testCheckSNMayExist(self):
    self._WriteRMAConfigYAML(file_path=self.rma_config, test_config=1)
    test_shopfloor = ShopFloor()
    test_shopfloor.data_dir = self.testdata
    test_shopfloor.LoadConfiguration(self.testdata)
    self.assertTrue(test_shopfloor.CheckSN("RMA99999999"))
    self.assertRaisesRegexp(ValueError, r"Invalid RMA number",
                            test_shopfloor.CheckSN, "BLAHBLAH")

  def testCheckSNMustExist(self):
    self._WriteRMAConfigYAML(file_path=self.rma_config, test_config=2)
    test_shopfloor = ShopFloor()
    test_shopfloor.data_dir = self.testdata
    test_shopfloor.LoadConfiguration(self.testdata)
    self.assertTrue(test_shopfloor.CheckSN("RMA00000000"))
    self.assertRaisesRegexp(ValueError, r"RMA YAML not found on shopfloor",
                            test_shopfloor.CheckSN, "RMA12345678")

  def testSaveDeviceDataSimple(self):
    # Simple data saving test
    self._WriteRMAConfigYAML(file_path=self.rma_config, test_config=1)
    test_shopfloor = ShopFloor()
    test_shopfloor.data_dir = self.testdata
    test_shopfloor.LoadConfiguration(self.testdata)
    device_data = {'hwid': _TEST_HWID, 'serial_number': 'RMA11111111',
                   'vpd': _TEST_VPD}
    ret = test_shopfloor.SaveDeviceData(device_data, True)
    self.assertEqual(ret['status'], 'success')
    yaml_file = os.path.join(self.testdata, _RMA11111111_FILE)
    self.assertTrue(os.path.isfile(yaml_file))
    with open(yaml_file, 'rb') as f:
      yaml_content = f.read()
    self.assertEqual(yaml_content, _RMA11111111_YAML_1)
    if os.path.isfile(os.path.join(self.testdata, _RMA11111111_FILE)):
      os.remove(os.path.join(self.testdata, _RMA11111111_FILE))

  def testSaveDeviceDataAdvanced(self):
    # Advanced data saving test with translation
    self._WriteRMAConfigYAML(file_path=self.rma_config, test_config=2)
    with open(self.rma_config, 'a') as f:
      f.write('hwidv3_hwdb_path: %s' % self.testdata)
    test_shopfloor = ShopFloor()
    test_shopfloor.data_dir = self.testdata
    test_shopfloor.LoadConfiguration(self.testdata)
    device_data = {'hwid': _TEST_HWID, 'serial_number': 'RMA11111111',
                   'vpd': _TEST_VPD}
    ret = test_shopfloor.SaveDeviceData(device_data, True)
    self.assertEqual(ret['status'], 'success')
    yaml_file = os.path.join(self.testdata, _RMA11111111_FILE)
    self.assertTrue(os.path.isfile(yaml_file))
    with open(yaml_file, 'rb') as f:
      yaml_content = f.read()
    self.assertEqual(yaml_content, _RMA11111111_YAML_2)
    if os.path.isfile(os.path.join(self.testdata, _RMA11111111_FILE)):
      os.remove(os.path.join(self.testdata, _RMA11111111_FILE))

if __name__ == '__main__':
  unittest.main()
