#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=E1101

import logging
import os
import unittest

import factory_common   # pylint: disable=W0611
import cros.factory.hwid.v3.common_rule_functions  # pylint: disable=W0611
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.common import HWIDException
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import transformer
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.hwid.v3.hwid_rule_functions import ComponentEq
from cros.factory.hwid.v3.hwid_rule_functions import ComponentIn
from cros.factory.hwid.v3.hwid_rule_functions import GetClassAttributesOnBOM
from cros.factory.hwid.v3.hwid_rule_functions import GetDeviceInfo
from cros.factory.hwid.v3.hwid_rule_functions import GetPhase
from cros.factory.hwid.v3.hwid_rule_functions import GetVPDValue
from cros.factory.hwid.v3.hwid_rule_functions import SetComponent
from cros.factory.hwid.v3.hwid_rule_functions import SetImageId
from cros.factory.hwid.v3.rule import Context
from cros.factory.hwid.v3.rule import GetLogger
from cros.factory.hwid.v3.rule import Rule
from cros.factory.hwid.v3.rule import RuleException
from cros.factory.hwid.v3.rule import SetContext
from cros.factory.hwid.v3 import yaml_wrapper as yaml
from cros.factory.test.rules import phase
from cros.factory.utils import json_utils

_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


class HWIDRuleTest(unittest.TestCase):

  def setUp(self):
    self.database = Database.LoadFile(os.path.join(_TEST_DATA_PATH,
                                                   'test_db.yaml'))
    self.results = json_utils.LoadFile(
        os.path.join(_TEST_DATA_PATH, 'test_probe_result.json'))
    self.bom = hwid_utils.GenerateBOMFromProbedResults(self.database,
                                                       self.results[0])
    self.database.UpdateComponentsOfBOM(self.bom, {
        'keyboard': 'keyboard_us', 'dram': 'dram_0',
        'display_panel': 'display_panel_0'})
    self.device_info = {
        'SKU': 1,
        'has_cellular': False
    }
    self.vpd = {
        'ro': {
            'serial_number': 'foo',
            'region': 'us'
        },
        'rw': {
            'registration_code': 'buz'
        }
    }
    self.context = Context(
        database=self.database, bom=self.bom,
        mode=common.OPERATION_MODE.normal,
        device_info=self.device_info, vpd=self.vpd)
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
    identity = transformer.BOMToIdentity(self.database, self.bom)
    self.assertEquals(identity.encoded_string, r'CHROMEBOOK AA5Q-YM2')

    rule = Rule(name='foobar2',
                when="GetDeviceInfo('SKU') == 1",
                evaluate=[
                    "Assert(ComponentEq('cpu', 'cpu_3'))"],
                otherwise=None)
    self.assertRaisesRegexp(
        RuleException, r'ERROR: Assertion failed',
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
        SyntaxError, r'unexpected EOF while parsing', rule.Validate)
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
        SyntaxError, r'invalid syntax \(<string>, line 1\)', rule.Validate)

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
    identity = transformer.BOMToIdentity(self.database, self.bom)
    self.assertEquals(identity.encoded_string, r'CHROMEBOOK AA5Q-YM2')

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
        RuleException, r'ERROR: Assertion failed.',
        rule.Evaluate, self.context)

    rule = yaml.load("""
        !rule
        name: foobar2
        when: GetDeviceInfo('SKU') == 1
        evaluate: Assert(ComponentEq('cpu', 'cpu_3'))
    """)
    self.assertRaisesRegexp(
        RuleException, r'ERROR: Assertion failed.',
        rule.Evaluate, self.context)

    rule = yaml.load("""
        !rule
        name: foobar3
        when: Re('us').Matches(GetVPDValue('ro', 'region'))
        evaluate: Assert(ComponentEq('cpu', 'cpu_3'))
    """)
    self.assertRaisesRegexp(
        RuleException, r'ERROR: Assertion failed.',
        rule.Evaluate, self.context)

  def testGetClassAttributesOnBOM(self):
    cpu_attrs = GetClassAttributesOnBOM(self.database, self.bom, 'cpu')
    self.assertEquals(['cpu_5'], cpu_attrs)

    self.assertEquals(
        None, GetClassAttributesOnBOM(self.database, self.bom, 'foo'))
    self.assertEquals("ERROR: Invalid component class: 'foo'",
                      GetLogger().error[0].message)

  def testComponentEq(self):
    self.assertTrue(ComponentEq('cpu', 'cpu_5'))
    self.assertFalse(ComponentEq('cpu', 'cpu_3'))

  def testComponentIn(self):
    self.assertTrue(
        ComponentIn('cpu', ['cpu_3', 'cpu_4', 'cpu_5']))
    self.assertFalse(
        ComponentIn('cpu', ['cpu_3', 'cpu_4']))

  def testSetComponent(self):
    SetComponent('cpu', 'cpu_3')
    self.assertEquals(
        'cpu_3', self.context.bom.components['cpu'][0].component_name)
    self.assertEquals(
        3, self.context.bom.encoded_fields['cpu'])
    identity = transformer.BOMToIdentity(self.database, self.bom)
    self.assertEquals('CHROMEBOOK AA5E-IVL', identity.encoded_string)
    SetComponent('cellular', 'cellular_0')
    self.assertEquals(
        'cellular_0',
        self.context.bom.components['cellular'][0].component_name)
    self.assertEquals(1, self.context.bom.encoded_fields['cellular'])
    identity = transformer.BOMToIdentity(self.database, self.bom)
    self.assertEquals('CHROMEBOOK AA7E-IWF', identity.encoded_string)

  def testSetImageId(self):
    SetImageId(1)
    identity = transformer.BOMToIdentity(self.database, self.bom)
    self.assertEquals('CHROMEBOOK BA5A-YI3', identity.encoded_string)
    SetImageId(2)
    identity = transformer.BOMToIdentity(self.database, self.bom)
    self.assertEquals('CHROMEBOOK C2H-I3Q-A6Q', identity.encoded_string)
    self.assertRaisesRegexp(
        HWIDException, r'Invalid image id: 7', SetImageId, 7)

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

  def testGetPhase(self):
    # Should be 'PVT' when no build phase is set.
    self.assertEquals('PVT', GetPhase())
    phase._current_phase = phase.PROTO  # pylint: disable=protected-access
    self.assertEquals('PROTO', GetPhase())
    phase._current_phase = phase.PVT_DOGFOOD  # pylint: disable=protected-access
    self.assertEquals('PVT_DOGFOOD', GetPhase())


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
