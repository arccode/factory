#!/bin/env python
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.hwid.v3 import yaml_tags


class RegionFieldUnittest(unittest.TestCase):

  def testRegionFieldDict(self):
    regions_field = yaml_tags.RegionField()
    self.assertEquals({'region': 'us'}, regions_field[29])
    self.assertTrue(regions_field.is_legacy_style)

  def testYamlNode(self):
    nodes = [yaml_tags.YamlNode('tw'), yaml_tags.YamlNode('jp')]
    obj = yaml_tags.RegionField(nodes)
    self.assertEquals(obj.GetRegions(), ['tw', 'jp'])

  def testDecodeYAMLTag(self):
    YAML_DOC = 'foo: !region_field'
    decoded = yaml.load(YAML_DOC)
    self.assertEquals({'region': 'us'}, decoded['foo'][29])
    self.assertTrue(decoded['foo'].is_legacy_style)

  def testDumpRegionField(self):
    YAML_DOC = 'foo: !region_field [us, gb]'
    decoded = yaml.load(YAML_DOC)
    self.assertIsInstance(decoded['foo'], yaml_tags.RegionField)
    self.assertFalse(decoded['foo'].is_legacy_style)
    self.assertEquals(decoded['foo'], {
        0: {'region': None},
        1: {'region': 'us'},
        2: {'region': 'gb'}})
    dump_str = yaml.dump(decoded).strip()
    self.assertEquals(YAML_DOC, dump_str)

  def testDumpLegacyRegionField(self):
    YAML_DOC = 'foo: !region_field'
    decoded = yaml.load(YAML_DOC)
    dump_str = yaml.dump(decoded, default_flow_style=False).strip()
    self.assertEquals(yaml_tags.RemoveDummyString(dump_str), YAML_DOC)

  def testUnsupportRegionField(self):
    YAML_DOC = "foo: !region_field [us, NO_THIS_REGION]"
    with self.assertRaises(KeyError):
      yaml.load(YAML_DOC)

  def testAddRegions(self):
    YAML_DOC = '!region_field [us, gb]'
    decoded = yaml.load(YAML_DOC)
    self.assertEquals(decoded.GetRegions(), ['us', 'gb'])
    decoded.AddRegion('jp')
    self.assertEquals(decoded.GetRegions(), ['us', 'gb', 'jp'])
    self.assertFalse(decoded.is_legacy_style)

    obj = yaml_tags.RegionField()
    with self.assertRaises(ValueError):
      obj.AddRegion('us')

  def testIsLegacyStyleProperty(self):
    regions_field = yaml_tags.RegionField()
    with self.assertRaises(AttributeError):
      regions_field.is_legacy_style = True


class RegionComponentUnittest(unittest.TestCase):

  def testRegionComponentDict(self):
    regions_component = yaml_tags.RegionComponent()
    self.assertEquals(
        {'values': {
            'region_code': 'us'}},
        regions_component['items']['us'])

  def testDumpRegionComponent(self):
    YAML_DOC = '!region_component'
    obj = yaml.load(YAML_DOC)
    self.assertIsInstance(obj, yaml_tags.RegionComponent)

    # Because PyYaml cannot only output the tag, we only check the dump string
    # is equivalent to the original one, which mean the loaded object is the
    # same.
    dump_str = yaml.dump(obj)
    obj2 = yaml.load(dump_str)
    self.assertEquals(obj, obj2)

if __name__ == '__main__':
  unittest.main()
