#!/usr/bin/python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for regions.py."""

import logging
import os
import re
import StringIO
import unittest
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.l10n import regions, regions_unittest_data

# pylint: disable=W0212


def _FindAllStrings(c_source):
  """Returns a set of all strings in a C source file."""
  return set(re.findall(r'"(.+?)"', c_source))


class RegionTest(unittest.TestCase):
  """Tests for the Region class."""
  def testZoneInfo(self):
    all_regions = regions.BuildRegionsDict(include_all=True)

    # Make sure all time zones are present in /usr/share/zoneinfo.
    all_zoneinfos = [os.path.join('/usr/share/zoneinfo', r.time_zone)
                     for r in all_regions.values()]
    missing = [z for z in all_zoneinfos if not os.path.exists(z)]
    self.assertFalse(missing,
                     ('Missing zoneinfo files; are timezones misspelled?: %r' %
                      missing))

  def testTimeZones(self):
    zones = _FindAllStrings(regions_unittest_data.CROS_TIME_ZONES)

    for r in regions.BuildRegionsDict(include_all=True).values():
      if r.time_zone not in zones:
        if r.region_code in regions.REGIONS:
          self.fail(
            'Missing time zone %r; does a new time zone need to be added '
            'to CrOS, or does regions_unittest_data need to be updated?',
            r.time_zone)
        else:
          # This is an unconfirmed region; just print a warning.
          logging.warn('Missing time zone %r; does a new time zone need to be '
                       'added to CrOS, or does regions_unittest_data need to '
                       'be updated? (just a warning, since region '
                       '%r is not a confirmed region)',
                       r.time_zone, r.region_code)

  def testLanguages(self):
    languages = _FindAllStrings(regions_unittest_data.CROS_ACCEPT_LANGUAGE_LIST)
    missing = [
      r.language_code
      for r in regions.BuildRegionsDict(include_all=True).values()
      if r.language_code not in languages]
    self.assertFalse(
      missing,
      ('Missing languages; does regions_unittest_data need to be updated?: %r' %
       missing))

  def testInputMethods(self):
    methods = regions_unittest_data.CROS_INPUT_METHODS.splitlines()
    # Remove comments and strip whitespace
    methods = [re.sub('#.+', '', x).strip() for x in methods]
    # Remove empty lines
    methods = filter(None, methods)
    # Split into tuples
    methods = [x.split() for x in methods]
    # Turn into a dict based on the first field.
    methods_dict = dict([(x[0], x) for x in methods])

    # Verify that every region is present in the dict.
    for r in regions.BuildRegionsDict(include_all=True).values():
      method = methods_dict.get(r.keyboard)
      # Make sure the keyboard method is present.
      self.assertTrue(method, 'Missing keyboard layout %r' % r.keyboard)

  def testVPDSettings(self):
    self.assertEquals(
      {'initial_locale': 'en-US',
       'initial_timezone': 'America/Los_Angeles',
       'keyboard': 'xkb:us::eng',
       'region': 'us'},
      regions.BuildRegionsDict()['us'].GetVPDSettings())

  def testYAMLOutput(self):
    output = StringIO.StringIO()
    regions.main(['--format', 'yaml'], output)
    data = yaml.load(output.getvalue())
    self.assertEquals(
      {'keyboard': 'xkb:us::eng',
       'keyboard_mechanical_layout': 'ANSI',
       'language_code': 'en-US',
       'region_code': 'us',
       'time_zone': 'America/Los_Angeles',
       'vpd_settings': {'initial_locale': 'en-US',
                        'initial_timezone': 'America/Los_Angeles',
                        'keyboard': 'xkb:us::eng',
                        'region': 'us'}},
      data['us'])

  def testFieldsDict(self):
    # 'description' and 'notes' should be missing.
    self.assertEquals(
      {'keyboard': 'b',
       'keyboard_mechanical_layout': 'e',
       'language_code': 'd',
       'region_code': 'a',
       'time_zone': 'c'},
      (regions.Region('a', 'b', 'c', 'd', 'e', 'description', 'notes').
       GetFieldsDict()))

  def testConsolidateRegionsDups(self):
    """Test duplicate handling.  Two identical Regions are OK."""
    # Make two copies of the same region.
    region_list = [regions.Region('a', 'b', 'c', 'd', 'e') for _ in range(2)]
    # It's OK.
    self.assertEquals(
      {'a': region_list[0]}, regions._ConsolidateRegions(region_list))

    # Modify the second copy.
    region_list[1].keyboard = 'f'
    # Not OK anymore!
    self.assertRaisesRegexp(
      regions.RegionException, "Conflicting definitions for region 'a':",
      regions._ConsolidateRegions, region_list)

if __name__ == '__main__':
  unittest.main()
