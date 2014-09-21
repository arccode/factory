#!/bin/env python
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest
import yaml

import factory_common # pylint: disable=W0611
from cros.factory.hwid import yaml_tags


class RegionFieldUnittest(unittest.TestCase):
  def testRegionFieldDict(self):
    regions_field = yaml_tags.RegionField()
    self.assertEquals({'region': 'us'}, regions_field[29])

  def testDecodeYAMLTag(self):
    YAML_DOC = 'foo: !region_field'
    decoded = yaml.load(YAML_DOC)
    self.assertEquals({'region': 'us'}, decoded['foo'][29])


class RegionComponentUnittest(unittest.TestCase):
  def testRegionComponentDict(self):
    regions_component = yaml_tags.RegionComponent()
    self.assertEquals(
        {'values': {
            'region_code': 'us',
            'keyboards': 'xkb:us::eng',
            'time_zone': 'America/Los_Angeles',
            'language_codes': 'en-US',
            'keyboard_mechanical_layout': 'ANSI'}},
        regions_component['items']['us'])


if __name__ == '__main__':
  unittest.main()
