#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=E1101

import logging
import os
import unittest
import yaml

import factory_common   # pylint: disable=W0611
import cros.factory.common_rule_functions   #pylint: disable=W0611
from cros.factory.hwid.common import HWIDException
from cros.factory.hwid.database import Database
from cros.factory.hwid.encoder import Encode
from cros.factory.hwid.hwid_rule_functions import (
    GetClassAttributesOnBOM, ComponentEq, ComponentIn,
    SetComponent, SetImageId, GetDeviceInfo, GetVPDValue, ValidVPDValue,
    CheckRegistrationCode)
from cros.factory.rule import (
    Rule, Context, RuleException, SetContext, GetLogger)

_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


class HWIDRuleTest(unittest.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(os.path.join(_TEST_DATA_PATH,
                                                   'test_db.yaml'))
    self.results = [
        yaml.dump(result) for result in yaml.load_all(open(os.path.join(
            _TEST_DATA_PATH, 'test_probe_result.yaml')).read())]
    bom = self.database.ProbeResultToBOM(self.results[0])
    bom = self.database.UpdateComponentsOfBOM(bom, {
        'keyboard': 'keyboard_us', 'dram': 'dram_0',
        'display_panel': 'display_panel_0'})
    self.hwid = Encode(self.database, bom)
    self.device_info = {
      'SKU': 1,
      'has_cellular': False
    }
    self.vpd = {
      'ro': {
        'serial_number': 'foo',
        'initial_locale': 'en-us'
      },
      'rw': {
        'registration_code': 'buz'
      }
    }
    self.context = Context(hwid=self.hwid, device_info=self.device_info,
                           vpd=self.vpd)
    SetContext(self.context)

  def testRule(self):
    # Original binary string: 0000000000111010000011
    # Original encoded string: CHROMEBOOK AA5A-Y6L
    rule = Rule(name='foobar1',
                when="GetDeviceInfo('SKU') == 1",
                evaluate=[
                    "Assert(ComponentEq('cpu', 'cpu_5'))",
                    "Assert(ComponentEq('cellular', None))",
                    "SetComponent('dram', 'dram_1')"],
                otherwise=None)
    rule.Evaluate(self.context)
    self.assertEquals(self.hwid.binary_string, r'0000000000111011000011')
    self.assertEquals(self.hwid.encoded_string, r'CHROMEBOOK AA5Q-YM2')

    rule = Rule(name='foobar2',
                when="GetDeviceInfo('SKU') == 1",
                evaluate=[
                    "Assert(ComponentEq('cpu', 'cpu_3'))"],
                otherwise=None)
    self.assertRaisesRegexp(
        RuleException, r"ERROR: Assertion failed",
        rule.Evaluate, self.context)

  def testYAMLParsing(self):
    rule = yaml.load("""
            !rule
            name: foobar1
            when: GetDeviceInfo('SKU' == 1
            evaluate:
            - Assert(ComponentEq('cpu', 'cpu_5')
            - Assert(ComponentEq('cellular', None))
            - SetComponent('dram', 'dram_1')
        """)
    self.assertRaisesRegexp(
        SyntaxError, r"unexpected EOF while parsing", rule.Validate)
    rule = yaml.load("""
            !rule
            name: foobar1
            when: GetDeviceInfo('SKU') == 1
            evaluate:
            - Assert(ComponentEq('cpu', 'cpu_5'))
            - Assert(ComponentEq'cellular', None))
            - SetComponent('dram', 'dram_1')
        """)
    self.assertRaisesRegexp(
        SyntaxError, r"invalid syntax \(<string>, line 1\)", rule.Validate)

    rule = yaml.load("""
        !rule
        name: foobar1
        when: >
          (GetDeviceInfo('SKU') == 1) and
          (GetDeviceInfo('has_cellular') == False)
        evaluate:
        - Assert(ComponentEq('cpu', 'cpu_5'))
        - Assert(ComponentEq('cellular', None))
        - SetComponent('dram', 'dram_1')
    """)
    rule.Evaluate(self.context)
    self.assertEquals(self.hwid.binary_string, r'0000000000111011000011')
    self.assertEquals(self.hwid.encoded_string, r'CHROMEBOOK AA5Q-YM2')

    rule = yaml.load("""
        !rule
        name: foobar2
        when: ComponentEq('cpu', Re('cpu_.'))
        evaluate: Assert(ComponentEq('cellular', None))
    """)
    self.assertEquals(None, rule.Evaluate(self.context))

    rule = yaml.load("""
        !rule
        name: foobar2
        when: ComponentEq('cpu', Re('cpu_.'))
        evaluate: Assert(ComponentEq('cellular', 'cellular_0'))
    """)
    self.assertRaisesRegexp(
        RuleException, r"ERROR: Assertion failed.",
        rule.Evaluate, self.context)

    rule = yaml.load("""
        !rule
        name: foobar2
        when: GetDeviceInfo('SKU') == 1
        evaluate: Assert(ComponentEq('cpu', 'cpu_3'))
    """)
    self.assertRaisesRegexp(
        RuleException, r"ERROR: Assertion failed.",
        rule.Evaluate, self.context)

    rule = yaml.load("""
        !rule
        name: foobar3
        when: Re('en-.*').Matches(GetVPDValue('ro', 'initial_locale'))
        evaluate: Assert(ComponentEq('cpu', 'cpu_3'))
    """)
    self.assertRaisesRegexp(
        RuleException, r"ERROR: Assertion failed.",
        rule.Evaluate, self.context)

  def testGetClassAttributesOnBOM(self):
    cpu_attrs = GetClassAttributesOnBOM(self.hwid, 'cpu')
    self.assertEquals(['cpu_5'], cpu_attrs)
    storage_attrs = GetClassAttributesOnBOM(self.hwid, 'storage')
    self.assertEquals(['storage_0', 'SSD', '16G'], storage_attrs)

    self.assertEquals(None, GetClassAttributesOnBOM(self.hwid, 'foo'))
    self.assertEquals("ERROR: Invalid component class: 'foo'",
                      GetLogger().error[0].message)

  def testComponentEq(self):
    self.assertTrue(ComponentEq('cpu', 'cpu_5'))
    self.assertTrue(
        ComponentEq('storage', ['SSD', '16G']))
    self.assertFalse(ComponentEq('cpu', 'cpu_3'))
    self.assertFalse(
        ComponentEq('storage', ['SSD', '32G']))

  def testComponentIn(self):
    self.assertTrue(
        ComponentIn('cpu', ['cpu_3', 'cpu_4', 'cpu_5']))
    self.assertTrue(
        ComponentIn('storage', ['16G', '32G']))
    self.assertFalse(
        ComponentIn('cpu', ['cpu_3', 'cpu_4']))

  def testSetComponent(self):
    SetComponent('cpu', 'cpu_3')
    self.assertEquals(
        'cpu_3', self.context.hwid.bom.components['cpu'][0].component_name)
    self.assertEquals(
        3, self.context.hwid.bom.encoded_fields['cpu'])
    self.assertEquals('0000000000111010010001', self.hwid.binary_string)
    self.assertEquals('CHROMEBOOK AA5E-IVL', self.hwid.encoded_string)
    SetComponent('cellular', 'cellular_0')
    self.assertEquals(
        'cellular_0',
        self.context.hwid.bom.components['cellular'][0].component_name)
    self.assertEquals(
        1, self.context.hwid.bom.encoded_fields['cellular'])
    self.assertEquals('0000000000111110010001', self.hwid.binary_string)
    self.assertEquals('CHROMEBOOK AA7E-IWF', self.hwid.encoded_string)

  def testSetImageId(self):
    SetImageId(1)
    self.assertEquals('0000100000111010000011', self.hwid.binary_string)
    self.assertEquals('CHROMEBOOK BA5A-YI3', self.hwid.encoded_string)
    SetImageId(2)
    self.assertEquals('0001000000111010000011', self.hwid.binary_string)
    self.assertEquals('CHROMEBOOK C2H-I3Q-A6Q', self.hwid.encoded_string)
    self.assertRaisesRegexp(
        HWIDException, r'Invalid image id: 7', SetImageId, 7)

  def testValidVPDValue(self):
    mock_vpd = {
        'ro': {
            'initial_locale': 'en-US',
            'initial_timezone': 'America/Los_Angeles',
            'keyboard_layout': 'xkb:us::eng',
            'serial_number': 'foobar'
        }
    }
    SetContext(Context(vpd=mock_vpd))
    self.assertEquals(True, ValidVPDValue('ro', 'initial_locale'))
    self.assertEquals(True, ValidVPDValue('ro', 'initial_timezone'))
    self.assertEquals(True, ValidVPDValue('ro', 'keyboard_layout'))
    self.assertEquals(True, ValidVPDValue('ro', 'serial_number'))

    mock_vpd = {
        'ro':{
            'initial_locale': 'foo'
        }
    }
    SetContext(Context(vpd=mock_vpd))
    self.assertFalse(ValidVPDValue('ro', 'initial_locale'))
    self.assertEquals("ERROR: Invalid VPD value 'foo' of 'initial_locale'",
                      GetLogger().error[0].message)

    mock_vpd = {
        'ro':{
            'initial_timezone': 'foo'
        }
    }
    SetContext(Context(vpd=mock_vpd))
    self.assertFalse(ValidVPDValue('ro', 'initial_timezone'))
    self.assertEquals("ERROR: Invalid VPD value 'foo' of 'initial_timezone'",
                      GetLogger().error[0].message)

    mock_vpd = {
        'ro':{
            'keyboard_layout': 'foo'
        }
    }
    SetContext(Context(vpd=mock_vpd))
    self.assertFalse(ValidVPDValue('ro', 'keyboard_layout'))
    self.assertEquals("ERROR: Invalid VPD value 'foo' of 'keyboard_layout'",
                      GetLogger().error[0].message)


  def testCheckRegistrationCode(self):
    mock_gbind_attribute = ('3333333333333333333333333333333333333'
                            '3333333333333333333333333332dbecc73')
    mock_ubind_attribute = ('3232323232323232323232323232323232323'
                            '23232323232323232323232323256850612')
    self.assertEquals(None, CheckRegistrationCode(mock_gbind_attribute))
    self.assertEquals(None, CheckRegistrationCode(mock_ubind_attribute))
    mock_gbind_attribute = 'foo'
    self.assertRaisesRegexp(
        ValueError, r"Registration code 'foo' is not 72 characters long",
        CheckRegistrationCode, mock_gbind_attribute)

  def testGetDeviceInfo(self):
    self.assertEquals(1, GetDeviceInfo('SKU'))
    self.assertEquals(
        False, GetDeviceInfo('has_cellular'))

  def testGetDeviceInfoDefault(self):
    self.assertEquals(1, GetDeviceInfo('SKU'))
    self.assertEquals(
        'Default', GetDeviceInfo('has_something', 'Default'))

  def testGetVPDValue(self):
    self.assertEquals(
        'foo', GetVPDValue('ro', 'serial_number'))
    self.assertEquals(
        'buz', GetVPDValue('rw', 'registration_code'))

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
