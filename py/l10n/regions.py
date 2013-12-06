#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Authoritative source for factory region/locale configuration.

Run this module to display all known regions (use --help to see options).
"""


import argparse
import collections
import sys

import factory_common  # pylint: disable=W0611
from cros.factory.test.utils import Enum


KeyboardMechanicalLayout = Enum(['ANSI', 'ISO', 'JIS'])


class Region(object):
  """Comprehensive, standard locale configuration per country/region.

  Properties:
    code: The lowercase alpha-2 country/region code (from ISO
      3166-1). Note that this is "gb", not "uk", for the United
      Kingdom. If in the future we need to handle groups of countries,
      or country subdivisions (e.g., sub-country SKUs), we could
      loosen the requirement that this is strictly an alpha-2 code
      (e.g., add "ch.fr-CH" for a Swiss French configuration, or
      "xx-south-america" for a South American configuration).
    keyboard: The standard keyboard layout (e.g., 'xkb:us:intl:eng'); see
      http://goo.gl/3aJnl and http://goo.gl/xWNrUP.
    time_zone: The standard time zone (e.g., 'America/Los_Angeles'); see
      http://goo.gl/WSVUeE.
    language code: The standard language code (e.g., 'en-US'); see
      http://goo.gl/kVkht.
    keyboard_mechanical_layout: The keyboard's mechanical layout (ANSI
      [US-like], ISO [UK-like], or JIS).
  """
  FIELDS = ['region_code', 'keyboard', 'time_zone', 'language_code',
            'keyboard_mechanical_layout']

  def __init__(self, region_code, keyboard, time_zone, language_code,
               keyboard_mechanical_layout):
    # Quick check: should be 'gb', not 'uk'
    assert region_code != 'uk'

    self.region_code = region_code
    self.keyboard = keyboard
    self.time_zone = time_zone
    self.language_code = language_code
    self.keyboard_mechanical_layout = keyboard_mechanical_layout


_KML = KeyboardMechanicalLayout
REGIONS_LIST = [
    Region('us', 'xkb:us::eng',     'America/Los_Angeles', 'en-US', _KML.ANSI),
    Region('gb', 'xkb:gb:extd:eng', 'Europe/London',       'en-GB', _KML.ISO),
]

# These are believed to be correct but unconfirmed, and all fields
# should be verified (and the row moved into REGIONS_LIST) before
# launch.  See <http://goto/vpdsettings>.
#
# Note that currently non-Latin keyboards must use underlying Latin
# keyboard for VPD.  (This assumption should be revisited when moving
# items from UNCONFIRMED_REGIONS to REGIONS.)  This is currently being
# discussed on <http://crbug.com/325389>.
#
# Note that some timezones may be missing from timezone_settings.cc
# (see http://crosbug.com/p/23902).
UNCONFIRMED_REGIONS_LIST = []

# The following regions may contain incorrect information, and all
# fields must be reviewed before launch.  See <http://goto/vpdsettings>.
INCOMPLETE_REGIONS_LIST = []


def BuildRegionsDict(include_all=False):
  """Builds a dictionary of region code to
  :py:class:py.l10n.regions.Region: object.

  The regions include:

  - :py:data:`cros.factory.l10n.regions.REGIONS_LIST`
  - :py:data:`cros.factory.l10n.regions_overlay.REGIONS_LIST`
  - Only if ``include_all`` is true:
    - :py:data:`cros.factory.l10n.regions.UNCONFIRMED_REGIONS_LIST`
    - :py:data:`cros.factory.l10n.regions_overlay.UNCONFIRMED_REGIONS_LIST`
    - :py:data:`cros.factory.l10n.regions.INCOMPLETE_REGIONS_LIST`
    - :py:data:`cros.factory.l10n.regions_overlay.INCOMPLETE_REGIONS_LIST`

  A region may only appear in one of the above lists, or this function
  will (deliberately) fail.
  """
  regions = list(REGIONS_LIST)
  if include_all:
    regions += UNCONFIRMED_REGIONS_LIST + INCOMPLETE_REGIONS_LIST

  try:
    from cros.factory.l10n import regions_overlay   # pylint: disable=E0611
    # REGIONS_LIST must be present
    regions += regions_overlay.REGIONS_LIST
    if include_all:
      for name in ('UNCONFIRMED_REGIONS_LIST', 'INCOMPLETE_REGIONS_LIST'):
        regions += getattr(regions_overlay, name, [])
  except ImportError:
    pass

  region_codes = [r.region_code for r in regions]
  dups = sorted([
      k for k, v in collections.Counter(region_codes).iteritems() if v > 1])
  assert not dups, 'Duplicate region codes: %s' % dups

  return dict((x.region_code, x) for x in regions)


REGIONS = BuildRegionsDict()


def main():
  parser = argparse.ArgumentParser(description=(
      'Display all known regions and their parameters. '
      'To include any regions in the board overlay, run '
      '"make overlay-$BOARD && overlay-$BOARD/py/l10n/regions.py" '
      'from the platform/factory directory.'))
  parser.add_argument('--format', choices=('human-readable', 'csv'),
                      default='human-readable',
                      help='Output format (default=%(default)s)')
  parser.add_argument('--all', action='store_true',
                      help='Include unconfirmed and incomplete regions')
  args = parser.parse_args()

  # List of list of lines to print.
  lines = [Region.FIELDS]
  for region in sorted(BuildRegionsDict(args.all).values(),
                       key=lambda v: v.region_code):
    lines.append([getattr(region, field) for field in Region.FIELDS])

  if args.format == 'csv':
    # Just print the lines in CSV format.
    for l in lines:
      print ','.join(l)
  elif args.format == 'human-readable':
    num_columns = len(lines[0])

    # Calculate maximum length of each column.
    max_lengths = []
    for column_no in xrange(num_columns):
      max_lengths.append(max(len(line[column_no]) for line in lines))

    # Print each line, padding as necessary to the max column length.
    for line in lines:
      for column_no in xrange(num_columns):
        sys.stdout.write(line[column_no].ljust(max_lengths[column_no] + 2))
      sys.stdout.write('\n')


if __name__ == '__main__':
  main()
