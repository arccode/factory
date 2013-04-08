#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=W0212

import os
import unittest
import factory_common # pylint: disable=W0611

from cros.factory.hwid import Database
from cros.factory.hwid.rule_evaluator import RuleEvaluator
import cros.factory.hwid.encoder as Encoder

_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


class RuleEvaluatorTest(unittest.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(os.path.join(_TEST_DATA_PATH,
                                                   'test_db.yaml'))
    # Create testing HWID
    result = open(os.path.join(_TEST_DATA_PATH,
                               'test_probe_result.yaml'), 'r').read()
    bom = self.database.ProbeResultToBOM(result)
    # Manually set unprobeable components.
    bom = self.database.UpdateComponentsOfBOM(
        bom, {'camera': 'camera_0', 'display_panel': 'display_panel_0'})
    self.hwid = Encoder.Encode(self.database, bom)

  def testConvertYamlStringToSet(self):
    self.assertEquals(set(['a']),
                      RuleEvaluator._ConvertYamlStringToSet('a'))
    self.assertEquals(set(['a, b']),
                      RuleEvaluator._ConvertYamlStringToSet(' a, b '))
    self.assertEquals(set(['a', 'b']),
                      RuleEvaluator._ConvertYamlStringToSet('( a, b  )'))

  def testCheckAll(self):
    self.assertTrue(RuleEvaluator.CheckAll(
        self.hwid,
        ['battery EQ battery_huge',
         'cpu EQ cpu_5']))
    self.assertFalse(RuleEvaluator.CheckAll(
        self.hwid,
        ['battery EQ battery_huge',
         'cpu EQ CPU @ 2.40GHz [4 cores]']))
    self.assertTrue(RuleEvaluator.CheckAll(
        self.hwid,
        ['battery EQ battery_huge',
         'cpu EQ cpu_5',
         {'check_all': [
             'keyboard EQ keyboard_us',
             'storage EQ storage_0']}]))
    self.assertTrue(RuleEvaluator.CheckAll(
        self.hwid,
        ['battery EQ battery_huge',
         'cpu EQ cpu_5',
         {'check_all': [
             'keyboard EQ keyboard_us',
             'storage EQ storage_0']},
         {'check_any': [
             'dram EQ dram_1',
             'wireless EQ WIFI']}]))
    self.assertFalse(RuleEvaluator.CheckAll(
        self.hwid,
        ['battery EQ battery_huge',
         'cpu EQ cpu_5',
         {'check_all': [
             'keyboard EQ keyboard_gb',
             'storage EQ storage_0']},
         {'check_any': [
             'dram EQ dram_1',
             'wireless EQ WIFI']}]))

  def testCheckAny(self):
    self.assertTrue(RuleEvaluator.CheckAny(
        self.hwid,
        ['battery EQ battery_small',
         'cpu EQ CPU @ 2.80GHz [4 cores]']))
    self.assertFalse(RuleEvaluator.CheckAny(
        self.hwid,
        ['battery EQ battery_small',
         'cpu EQ cpu_1']))
    self.assertTrue(RuleEvaluator.CheckAny(
        self.hwid,
        ['battery EQ battery_small',
         'cpu EQ cpu_1',
         {'check_all': [
             'keyboard EQ keyboard_gb',
             'storage EQ storage_0']},
         {'check_any': [
             'dram EQ dram_1',
             'wireless EQ WIFI']}]))

  def testCheckCondition(self):
    self.assertTrue(RuleEvaluator.CheckCondition(
        self.hwid, 'battery EQ battery_huge'))
    self.assertFalse(RuleEvaluator.CheckCondition(
        self.hwid, 'cpu EQ cpu_2'))
    self.assertTrue(RuleEvaluator.CheckCondition(
        self.hwid, 'dram IN (dram_0, dram_1)'))
    self.assertFalse(RuleEvaluator.CheckCondition(
        self.hwid, 'storage IN (32G)'))
    self.assertTrue(RuleEvaluator.CheckCondition(
        self.hwid, 'cellular EQ None'))
    self.assertFalse(RuleEvaluator.CheckCondition(
        self.hwid, 'battery NE battery_huge'))
    self.assertTrue(RuleEvaluator.CheckCondition(
        self.hwid, 'cpu NOT_IN (cpu_0, cpu_1, cpu_2)'))
    self.assertFalse(RuleEvaluator.CheckCondition(
        self.hwid, 'cpu NOT_IN (cpu_4, cpu_5    )'))
    self.assertTrue(RuleEvaluator.CheckCondition(
        self.hwid, 'cpu IN *'))
    self.assertFalse(RuleEvaluator.CheckCondition(
        self.hwid, 'wimax IN *'))

  def testEvaluateRules(self):
    self.assertEquals(
        (['Test rule 1', 'Test rule 4', 'Test rule 5', 'Test rule 6'],
         ['Test rule 3'], ['Test rule 2']),
        RuleEvaluator.EvaluateRules(self.hwid, self.hwid.database.rules))

  def testVerifySKU(self):
    self.assertEquals(
        ['SKU1', 'SKU3'],
        RuleEvaluator.VerifySKU(self.hwid, self.hwid.database.allowed_skus))


if __name__ == '__main__':
  unittest.main()
