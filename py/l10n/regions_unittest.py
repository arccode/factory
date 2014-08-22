#!/usr/bin/python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for regions.py.

These tests ensure that all regions in regions.py (and
regions_overlay.py, if present) are valid.  The tests use testdata
pulled from the Chromium sources; use update_testdata.py to update.
"""

import logging
import os
import StringIO
import unittest
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.l10n import regions


# pylint: disable=W0212


class RegionTest(unittest.TestCase):
  """Tests for the Region class."""
  @classmethod
  def _ReadTestData(cls, name):
    """Reads a YAML-formatted test data file.

    Args:
      name: Name of file in the testdata directory.

    Returns: The parsed value.
    """
    with open(os.path.join(os.path.dirname(__file__),
                           'testdata', name + '.yaml')) as f:
      return yaml.load(f)

  @classmethod
  def setUpClass(cls):
    cls.languages = cls._ReadTestData('languages')
    cls.time_zones = cls._ReadTestData('time_zones')
    cls.migration_map = cls._ReadTestData('migration_map')
    cls.input_methods = cls._ReadTestData('input_methods')

  def _ResolveInputMethod(self, method):
    """Resolves an input method using the migration map.

    Args:
      method: An input method ID that may contain prefixes from the
          migration map.  (E.g., "m17n:ar", which contains the "m17n:" prefix.)

    Returns:
      The input method ID after mapping any prefixes.  (E.g., "m17n:ar" will
      be mapped to "vkd_".)
    """
    for k, v in self.migration_map:
      if method.startswith(k):
        method = v + method[len(k):]
    return method

  def testZoneInfo(self):
    all_regions = regions.BuildRegionsDict(include_all=True)

    # Make sure all time zones are present in /usr/share/zoneinfo.
    all_zoneinfos = [os.path.join('/usr/share/zoneinfo', r.time_zone)
                     for r in all_regions.values()]
    missing = [z for z in all_zoneinfos if not os.path.exists(z)]
    self.assertFalse(missing,
                     ('Missing zoneinfo files; are timezones misspelled?: %r' %
                      missing))

  def testBadLanguage(self):
    self.assertRaisesRegexp(
        AssertionError, "Language code 'en-us' does not match", regions.Region,
        'us', 'xkb:us::eng', 'America/Los_Angeles', 'en-us', 'ANSI')

  def testBadKeyboard(self):
    self.assertRaisesRegexp(
        AssertionError, "Keyboard pattern 'xkb:us::' does not match",
        regions.Region, 'us', 'xkb:us::', 'America/Los_Angeles', 'en-US',
        'ANSI')

  def testKeyboardRegexp(self):
    self.assertTrue(regions.KEYBOARD_PATTERN.match('xkb:us::eng'))
    self.assertTrue(regions.KEYBOARD_PATTERN.match('ime:ko:korean'))
    self.assertTrue(regions.KEYBOARD_PATTERN.match('m17n:ar'))
    self.assertFalse(regions.KEYBOARD_PATTERN.match('m17n:'))
    self.assertFalse(regions.KEYBOARD_PATTERN.match('foo_bar'))

  def testTimeZones(self):
    for r in regions.BuildRegionsDict(include_all=True).values():
      if r.time_zone not in self.time_zones:
        if r.region_code in regions.REGIONS:
          self.fail(
            'Missing time zone %r; does a new time zone need to be added '
            'to CrOS, or does testdata need to be updated?' %
            r.time_zone)
        else:
          # This is an unconfirmed region; just print a warning.
          logging.warn('Missing time zone %r; does a new time zone need to be '
                       'added to CrOS, or does testdata need to '
                       'be updated? (just a warning, since region '
                       '%r is not a confirmed region)',
                       r.time_zone, r.region_code)

  def testLanguages(self):
    missing = []
    for r in regions.BuildRegionsDict(include_all=True).values():
      for l in r.language_codes:
        if l not in self.languages:
          missing.append(l)
    self.assertFalse(
      missing,
      ('Missing languages; does testdata need to be updated?: %r' %
       missing))

  def testInputMethods(self):
    # Verify that every region is present in the dict.
    for r in regions.BuildRegionsDict(include_all=True).values():
      for k in r.keyboards:
        resolved_method = self._ResolveInputMethod(k)
        # Make sure the keyboard method is present.
        self.assertIn(
            resolved_method, self.input_methods,
            'Missing keyboard layout %r (resolved from %r)' % (
                resolved_method, k))

  def testFirmwareLanguages(self):
    bmpblk_dir = os.path.join(
      os.environ.get('CROS_WORKON_SRCROOT'), 'src', 'platform', 'bmpblk')
    if not os.path.exists(bmpblk_dir):
      logging.warn('Skipping testFirmwareLanguages, since %r is missing',
                   bmpblk_dir)
      return

    bmp_locale_dir = os.path.join(bmpblk_dir, 'strings', 'locale')
    for r in regions.BuildRegionsDict(include_all=True).values():
      for l in r.language_codes:
        paths = [os.path.join(bmp_locale_dir, l)]
        if '-' in l:
          paths.append(os.path.join(bmp_locale_dir, l.partition('-')[0]))
        if not any([os.path.exists(x) for x in paths]):
          if r.region_code in regions.REGIONS:
            self.fail(
              'For region %r, none of %r exists' % (r.region_code, paths))
          else:
            logging.warn('For region %r, none of %r exists; '
                         'just a warning since this region is not confirmed',
                         r.region_code, paths)

  def testVPDSettings(self):
    # US has only a single VPD setting, so this should be the same
    # regardless of allow_multiple.
    for allow_multiple in [True, False]:
      self.assertEquals(
        {'initial_locale': 'en-US',
         'initial_timezone': 'America/Los_Angeles',
         'keyboard_layout': 'xkb:us::eng',
         'region': 'us'},
        regions.BuildRegionsDict()['us'].GetVPDSettings(allow_multiple))

    region = regions.Region(
      'a', ['xkb:b::b1', 'xkb:b::b2'], 'c', ['d1', 'd2'], 'e')
    self.assertEquals(
      {'initial_locale': 'd1',
       'initial_timezone': 'c',
       'keyboard_layout': 'xkb:b::b1',
       'region': 'a'},
      region.GetVPDSettings(False))
    self.assertEquals(
      {'initial_locale': 'd1,d2',
       'initial_timezone': 'c',
       'keyboard_layout': 'xkb:b::b1,xkb:b::b2',
       'region': 'a'},
      region.GetVPDSettings(True))


  def testYAMLOutput(self):
    output = StringIO.StringIO()
    regions.main(['--format', 'yaml'], output)
    data = yaml.load(output.getvalue())
    self.assertEquals(
      {'keyboards': ['xkb:us::eng'],
       'keyboard_mechanical_layout': 'ANSI',
       'language_codes': ['en-US'],
       'region_code': 'us',
       'numeric_id': 28,
       'time_zone': 'America/Los_Angeles',
       'vpd_settings': {'initial_locale': 'en-US',
                        'initial_timezone': 'America/Los_Angeles',
                        'keyboard_layout': 'xkb:us::eng',
                        'region': 'us'}},
      data['us'])

  def testFieldsDict(self):
    # 'description' and 'notes' should be missing.
    self.assertEquals(
      {'keyboards': ['xkb:b::b'],
       'keyboard_mechanical_layout': 'e',
       'language_codes': ['d'],
       'numeric_id': 11,
       'region_code': 'a',
       'time_zone': 'c'},
      (regions.Region('a', 'xkb:b::b', 'c', 'd', 'e', 'description', 'notes',
                      11).GetFieldsDict()))

  def testConsolidateRegionsDups(self):
    """Test duplicate handling.  Two identical Regions are OK."""
    # Make two copies of the same region.
    region_list = [regions.Region('a', 'xkb:b::b', 'c', 'd', 'e')
                   for _ in range(2)]
    # It's OK.
    self.assertEquals(
      {'a': region_list[0]}, regions._ConsolidateRegions(region_list))

    # Modify the second copy.
    region_list[1].keyboards = ['f']
    # Not OK anymore!
    self.assertRaisesRegexp(
      regions.RegionException, "Conflicting definitions for region 'a':",
      regions._ConsolidateRegions, region_list)

  def testNumericIds(self):
    """Make sure that numeric IDs are unique, and all confirmed regions have a
    numeric ID."""
    numeric_ids = set()
    for region in regions.BuildRegionsDict(include_all=True).values():
      if region.numeric_id is not None:
        self.assertNotIn(region.numeric_id, numeric_ids,
                         'Duplicate numeric ID %d in %s' % (
            region.numeric_id, region.region_code))
        numeric_ids.add(region.numeric_id)

      # Confirmed regions only
      if region.region_code in regions.REGIONS:
        self.assertIsNotNone(region.numeric_id,
                             'Region %s has no numeric ID assigned' % (
            region.region_code))

if __name__ == '__main__':
  unittest.main()
