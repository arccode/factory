#!/bin/env python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for HWID v3 utility functions."""

import copy
import logging
import os
import re
import unittest2
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory import rule
from cros.factory.hwid import common
from cros.factory.hwid import database
from cros.factory.hwid import hwid_utils
from cros.factory.hwdb import hwid_tool
from cros.factory.test import phase


TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')

# pylint: disable=E1101


class HWIDv3UtilsTest(unittest2.TestCase):
  """Test cases for HWID v3 utilities."""

  def setUp(self):
    self.db = database.Database.LoadFile(
        os.path.join(TEST_DATA_PATH, 'TEST_BOARD'))
    self.probed_results = yaml.load(open(os.path.join(
        TEST_DATA_PATH, 'test_probe_result_hwid_utils.yaml')).read())
    self.vpd = {
        'ro': {
            'initial_locale': 'en-US',
            'initial_timezone': 'America/Los_Angeles',
            'keyboard_layout': 'xkb:us::eng',
            'serial_number': 'foo'
        },
        'rw': {
            'gbind_attribute': '333333333333333333333'
                               '33333333333333333333333333333333333333333332dbecc73',
            'ubind_attribute': '323232323232323232323'
                               '232323232323232323232323232323232323232323256850612'
        }
    }

  def testVerifyComponentsV3(self):
    """Test if the Gooftool.VerifyComponent() works properly.

    This test tries to probe four components [bluetooth, battery, cpu,
    audio_codec], where
      'bluetooth' returns a valid result.
      'battery' returns a false result.
      'cpu' does not return any result.
      'audio_codec' returns multiple results.
    """
    probed_results = yaml.load(hwid_tool.ProbeResults(
        found_probe_value_map={
            'bluetooth': {
                'idVendor': '0123',
                'idProduct': 'abcd',
                'bcd': '0001'},
            'battery': {
                'compact_str': 'fake value'},
            'audio_codec': [
                {'compact_str': 'Codec 1'},
                {'compact_str': 'HDMI 1'},
                {'compact_str': 'fake value'}]},
        missing_component_classes=[],
        found_volatile_values={},
        initial_configs={}).Encode())

    results = hwid_utils.VerifyComponents(
        self.db, probed_results,
        ['bluetooth', 'battery', 'cpu', 'audio_codec'])

    self.assertEquals(
        [('bluetooth_0',
          {'idVendor': rule.Value('0123'), 'idProduct': rule.Value('abcd'),
           'bcd': rule.Value('0001')},
          None)],
        results['bluetooth'])
    self.assertEquals(
        [(None, None, "Missing 'cpu' component")],
        results['cpu'])
    self.assertEquals(
        [(None, {'compact_str': 'fake value'},
          ("Invalid 'battery' component found with probe result "
           "{ 'compact_str': 'fake value'} "
           '(no matching name in the component DB)'))],
        results['battery'])
    self.assertEquals(
        [('codec_1', {'compact_str': rule.Value('Codec 1')}, None),
         ('hdmi_1', {'compact_str': rule.Value('HDMI 1')}, None),
         (None, {'compact_str': 'fake value'},
          ("Invalid 'audio_codec' component found with probe result "
           "{ 'compact_str': 'fake value'} "
           '(no matching name in the component DB)'))],
        results['audio_codec'])

  def testVerifyBadComponents3(self):
    """Tests VerifyComponents with invalid component class name."""
    probed_results = yaml.load(hwid_tool.ProbeResults(
        found_probe_value_map={},
        missing_component_classes=[],
        found_volatile_values={},
        initial_configs={}).Encode())

    self.assertRaises(common.HWIDException, hwid_utils.VerifyComponents,
                      self.db, probed_results, ['cpu', 'bad_class_name'])

  def testGenerateHWID(self):
    """Tests HWID generation."""
    device_info = {
        'component.has_cellular': False,
        'component.keyboard': 'us',
        'component.dram': 'foo',
        'component.audio_codec': 'set_1'
    }

    self.assertEquals(
        'CHROMEBOOK D9I-E4A-A2B',
        hwid_utils.GenerateHWID(
            self.db, self.probed_results,
            device_info, self.vpd, False).encoded_string)

    device_info = {
        'component.has_cellular': True,
        'component.keyboard': 'gb',
        'component.dram': 'foo',
        'component.audio_codec': 'set_1'
    }
    self.assertEquals(
        'CHROMEBOOK D92-E4A-A87',
        hwid_utils.GenerateHWID(
            self.db, self.probed_results,
            device_info, self.vpd, False).encoded_string)

    device_info = {
        'component.has_cellular': True,
        'component.keyboard': 'gb',
        'component.dram': 'foo',
        'component.audio_codec': 'set_0'
    }
    self.assertEquals(
        'CHROMEBOOK D52-E4A-A7E',
        hwid_utils.GenerateHWID(
            self.db, self.probed_results,
            device_info, self.vpd, False).encoded_string)

  def testVerifyHWID(self):
    """Tests HWID verification."""
    self.assertEquals(None, hwid_utils.VerifyHWID(
        self.db, 'CHROMEBOOK A5AU-LU', self.probed_results, self.vpd, False,
        phase.EVT))
    for current_phase in (phase.PVT, phase.PVT_DOGFOOD):
      self.assertEquals(None, hwid_utils.VerifyHWID(
          self.db, 'CHROMEBOOK D9I-F9U', self.probed_results, self.vpd, False,
          current_phase))

    # Check for mismatched phase.
    self.assertRaisesRegexp(
        common.HWIDException,
        re.escape("In DVT phase, expected an image name beginning with 'DVT' "
                  "(but 'CHROMEBOOK D9I-F9U' has image ID 'PVT2')"),
        hwid_utils.VerifyHWID,
        self.db, 'CHROMEBOOK D9I-F9U', self.probed_results, self.vpd, False,
        phase.DVT)

    # Check for missing RO VPD.
    vpd = copy.deepcopy(self.vpd)
    del vpd['ro']['serial_number']
    self.assertRaisesRegexp(
        rule.RuleException, r"KeyError\('serial_number',\)",
        hwid_utils.VerifyHWID, self.db, 'CHROMEBOOK D9I-F9U',
        self.probed_results, vpd, False, phase.PVT)

    # Check for invalid RO VPD.
    vpd = copy.deepcopy(self.vpd)
    vpd['ro']['keyboard_layout'] = 'invalid_layout'
    self.assertRaisesRegexp(
        rule.RuleException,
        r"Invalid VPD value 'invalid_layout' of 'keyboard_layout'",
        hwid_utils.VerifyHWID, self.db, 'CHROMEBOOK D9I-F9U',
        self.probed_results, vpd, False, phase.PVT)

    # Check for missing RW VPD.
    vpd = copy.deepcopy(self.vpd)
    del vpd['rw']['gbind_attribute']
    self.assertRaisesRegexp(
        rule.RuleException, r"KeyError\('gbind_attribute',\)",
        hwid_utils.VerifyHWID, self.db, 'CHROMEBOOK D9I-F9U',
        self.probed_results, vpd, False, phase.PVT)

    # Check for invalid RW VPD.
    vpd = copy.deepcopy(self.vpd)
    vpd['rw']['gbind_attribute'] = 'invalid_gbind_attribute'
    self.assertRaisesRegexp(
        rule.RuleException,
        r"Invalid registration code 'invalid_gbind_attribute'",
        hwid_utils.VerifyHWID, self.db, 'CHROMEBOOK D9I-F9U',
        self.probed_results, vpd, False, phase.PVT)

    probed_results = copy.deepcopy(self.probed_results)
    probed_results['found_probe_value_map']['audio_codec'][1] = {
        'compact_str': 'HDMI 2'}
    self.assertRaisesRegexp(
        common.HWIDException,
        (r"Component class 'audio_codec' is missing components: "
         r"\['hdmi_1'\]. Expected components are: \['codec_1', 'hdmi_1'\]"),
        hwid_utils.VerifyHWID, self.db, 'CHROMEBOOK D9I-F9U', probed_results,
        self.vpd, False, phase.PVT)

    probed_results = copy.deepcopy(self.probed_results)
    probed_results['found_probe_value_map']['cellular'] = {
        'idVendor': '89ab', 'idProduct': 'abcd', 'name': 'Cellular Card'}
    probed_results['missing_component_classes'].remove('cellular')
    self.assertRaisesRegexp(
        common.HWIDException,
        (r"Component class 'cellular' has extra components: "
         r"\['cellular_0'\]. Expected components are: None"),
        hwid_utils.VerifyHWID, self.db, 'CHROMEBOOK D9I-F9U', probed_results,
        self.vpd, False, phase.PVT)

    # Test pre-MP recovery/root keys.
    probed_results = copy.deepcopy(self.probed_results)
    probed_results['found_volatile_values']['key_root'].update(
        {'compact_str': 'kv3#key_root_premp'})
    probed_results['found_volatile_values']['key_recovery'].update(
        {'compact_str': 'kv3#key_recovery_premp'})
    # Pre-MP recovery/root keys are fine in DVT...
    self.assertEquals(None, hwid_utils.VerifyHWID(
        self.db, 'CHROMEBOOK B5AW-5W', probed_results, self.vpd, False,
        phase.DVT))
    # ...but not in PVT
    self.assertRaisesRegexp(
        common.HWIDException,
        'MP keys are required in PVT, but key_recovery component name is '
        "'key_recovery_premp' and key_root component name is 'key_root_premp'",
        hwid_utils.VerifyHWID, self.db, 'CHROMEBOOK D9I-F6A-A6B',
        probed_results, self.vpd, False, phase.PVT)

    # Test deprecated component.
    probed_results = copy.deepcopy(self.probed_results)
    probed_results['found_volatile_values']['ro_main_firmware'].update(
        {'compact_str': 'mv2#ro_main_firmware_1'})
    self.assertRaisesRegexp(
        common.HWIDException, r'Not in RMA mode. Found deprecated component of '
        r"'ro_main_firmware': 'ro_main_firmware_1'",
        hwid_utils.VerifyHWID, self.db, 'CHROMEBOOK D9I-H9T', probed_results,
        self.vpd, False, phase.PVT)

    # Test deprecated component is allowed in rma mode.
    self.assertEquals(None, hwid_utils.VerifyHWID(
        self.db, 'CHROMEBOOK D9I-H9T', probed_results, self.vpd, True,
        phase.PVT))

    # Test unqualified component.
    probed_results = copy.deepcopy(self.probed_results)
    probed_results['found_probe_value_map']['dram'].update(
        {'vendor': 'DRAM 2',
         'size': '8G'})
    self.assertRaisesRegexp(
        common.HWIDException, r'Found unqualified component of '
        r"'dram': 'dram_2' in Phase\(PVT\)",
        hwid_utils.VerifyHWID, self.db,
        'CHROMEBOOK D9I-E8A-A5F', probed_results,
        self.vpd, False, phase.PVT)

    # Test unqualified component is allowed in early builds: PROTO/EVT/DVT.
    self.assertEquals(None, hwid_utils.VerifyHWID(
        self.db, 'CHROMEBOOK A5AT-PC', probed_results, self.vpd, False,
        phase.EVT))


  def testDecodeHWID(self):
    """Tests HWID decoding."""
    self.assertEquals(
        {'audio_codec': 1, 'battery': 3, 'ec_flash_chip': 0, 'firmware': 0,
         'storage': 0, 'flash_chip': 0, 'bluetooth': 0,
         'embedded_controller': 0, 'camera': 0, 'display_panel': 0,
         'cellular': 0, 'keyboard': 0, 'dram': 0, 'chipset': 0, 'cpu': 5},
        hwid_utils.DecodeHWID(self.db, 'CHROMEBOOK D9I-F9U').bom.encoded_fields)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest2.main()
