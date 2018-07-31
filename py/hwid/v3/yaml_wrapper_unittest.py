#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import rule
from cros.factory.hwid.v3 import yaml_wrapper as yaml


class ParseRegionFieldUnittest(unittest.TestCase):
  def testDecodeYAMLTag(self):
    doc = 'foo: !region_field'
    decoded = yaml.load(doc)
    self.assertEquals({'region': 'us'}, decoded['foo'][29])
    self.assertTrue(decoded['foo'].is_legacy_style)

    doc = 'foo: !region_field [us, gb]'
    decoded = yaml.load(doc)
    self.assertFalse(decoded['foo'].is_legacy_style)
    self.assertEquals(decoded['foo'], {
        0: {'region': []},
        1: {'region': 'us'},
        2: {'region': 'gb'}})

  def testDumpRegionField(self):
    doc = 'foo: !region_field [us, gb]'
    decoded = yaml.load(doc)
    dump_str = yaml.dump(decoded).strip()
    self.assertEquals(doc, dump_str)

    doc = 'foo: !region_field'
    decoded = yaml.load(doc)
    dump_str = yaml.dump(decoded, default_flow_style=False).strip()
    self.assertEquals(doc, dump_str)


class ParseRegionComponentUnittest(unittest.TestCase):

  def testLoadRegionComponent(self):
    obj = yaml.load('!region_component')
    self.assertEquals({'values': {'region_code': 'us'}},
                      obj['items']['us'])

  def testDumpRegionComponent(self):
    doc = '!region_component\n'
    obj = yaml.load(doc)

    self.assertEquals(yaml.dump(obj), doc)


@rule.RuleFunction(['string'])
def StrLen():
  return len(rule.GetContext().string)


@rule.RuleFunction(['string'])
def AssertStrLen(length):
  logger = rule.GetLogger()
  if len(rule.GetContext().string) <= length:
    logger.Error('Assertion error')


class ValueYAMLTagTest(unittest.TestCase):
  def testYAMLParsing(self):
    self.assertEquals(yaml.load('!re abc'), rule.Value('abc', is_re=True))
    self.assertEquals(yaml.load(yaml.dump(rule.Value('abc', is_re=False))),
                      'abc')
    self.assertEquals(yaml.dump(rule.Value('abc', is_re=True)), "!re 'abc'\n")


if __name__ == '__main__':
  unittest.main()
