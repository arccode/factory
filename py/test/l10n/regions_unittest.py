#!/usr/bin/env python2
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for regions.py.

These tests ensure that if regions.py (reading region database) is working
correctly.
"""

import logging
import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.l10n import regions


# pylint: disable=protected-access


class RegionTest(unittest.TestCase):
  """Tests for the Region class."""

  def testZoneInfo(self):
    all_regions = regions.BuildRegionsDict(include_all=False)

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

  def testFirmwareLanguages(self):
    bmpblk_dir = os.path.join(
        os.environ.get('CROS_WORKON_SRCROOT'), 'src', 'platform', 'bmpblk')
    if not os.path.exists(bmpblk_dir):
      logging.warn('Skipping testFirmwareLanguages, since %r is missing',
                   bmpblk_dir)
      return

    bmp_locale_dir = os.path.join(bmpblk_dir, 'strings', 'locale')
    for r in regions.BuildRegionsDict(include_all=False).values():
      paths = []
      for l in r.language_codes:
        paths.append(os.path.join(bmp_locale_dir, l))
        if '-' in l:
          paths.append(os.path.join(bmp_locale_dir, l.partition('-')[0]))
        if any([os.path.exists(x) for x in paths]):
          break
      else:
        self.fail('For region %r, none of %r exists' % (r.region_code, paths))

  def testFieldsDict(self):
    # 'description' and 'notes' should be missing.
    self.assertEquals(
        {'keyboards': ['xkb:b::b'],
         'keyboard_mechanical_layout': 'e',
         'language_codes': ['d'],
         'region_code': 'a',
         'time_zone': 'c'},
        (regions.Region('a', 'xkb:b::b', 'c', 'd', 'e', 'description',
                        'notes').GetFieldsDict()))

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


if __name__ == '__main__':
  unittest.main()
