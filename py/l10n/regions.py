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
  """Comprehensive, standard locale configuration per country/region."""

  # pylint gets confused by some of the docstrings.
  # pylint: disable=C0322

  region_code = None
  """A unique identifier for the region.  This may be a lower-case
  `ISO 3166-1 alpha-2 code
  <http://en.wikipedia.org/wiki/ISO_3166-1_alpha-2>`_ (e.g., ``us``),
  a variant within an alpha-2 entity (e.g., ``ca.fr``), or an
  identifier for a collection of countries or entities (e.g.,
  ``latam-es-419`` or ``nordic``).  See :ref:`region-codes`.

  Note that ``uk`` is not a valid identifier; ``gb`` is used as it is
  the real alpha-2 code for the UK.
  """

  keyboard = None
  """An XKB keyboard layout identifier (e.g., ``xkb:us:intl:eng``);
  see `input_method_util.cc <http://goo.gl/3aJnl>`_ and
  `input_methods.txt <http://goo.gl/xWNrUP>`_ for supported keyboards.
  Note that the keyboard must be whitelisted for login, i.e.,
  the respective line in `input_methods.txt <http://goo.gl/xWNrUP>`_ must
  contain the ``login`` keyword.

  This is used to set the VPD ``keyboard_layout`` value."""

  time_zone = None
  """A `tz database time zone
  <http://en.wikipedia.org/wiki/List_of_tz_database_time_zones>`_
  identifier (e.g., ``America/Los_Angeles``). See
  `timezone_settings.cc <http://goo.gl/WSVUeE>`_ for supported time
  zones.

  This is used to set the VPD ``initial_timezone`` value."""

  language_code = None
  """The default language code (e.g., ``en-US``); see
  `l10n_util.cc <http://goo.gl/kVkht>`_ for supported languages.

  This is used to set the VPD ``initial_locale`` language."""

  keyboard_mechanical_layout = None
  """The keyboard's mechanical layout (``ANSI`` [US-like], ``ISO``
  [UK-like], or ``JIS``)."""

  description = None
  """A human-readable description of the region.
  This defaults to :py:attr:`region_code` if not set."""

  notes = None
  """Notes about the region.  This may be None."""

  FIELDS = ['region_code', 'keyboard', 'time_zone', 'language_code',
            'keyboard_mechanical_layout']

  def __init__(self, region_code, keyboard, time_zone, language_code,
               keyboard_mechanical_layout, description=None, notes=None):
    # Quick check: should be 'gb', not 'uk'
    assert region_code != 'uk'

    self.region_code = region_code
    self.keyboard = keyboard
    self.time_zone = time_zone
    self.language_code = language_code
    self.keyboard_mechanical_layout = keyboard_mechanical_layout
    self.description = description or region_code
    self.notes = notes

  def __repr__(self):
    return 'Region(%s)' % (', '.join([getattr(self, x) for x in self.FIELDS]))

_KML = KeyboardMechanicalLayout
REGIONS_LIST = [
    Region('au', 'xkb:us::eng', 'Australia/Sydney', 'en-AU', _KML.ANSI,
           'Australia'),
    Region('ca.ansi', 'xkb:us::eng', 'America/Toronto', 'en-CA', _KML.ANSI,
           'Canada (US keyboard)',
           'Canada with US (ANSI) keyboard; see http://goto/cros-canada'),
    Region('ca.fr', 'xkb:ca::fra', 'America/Toronto', 'fr-CA', _KML.ISO,
           'Canada (French keyboard)',
           ('Device shipping to Canada with a purely Canadian French (ISO) '
            'keyboard; see http://goto/cros-canada')),
    Region('ca.hybrid', 'xkb:ca:eng:eng', 'America/Toronto', 'en-CA', _KML.ISO,
           'Canada (hybrid)',
           ('Canada with hybrid xkb:ca:eng:eng + xkb:ca::fra keyboard (ISO), '
            'defaulting to English language and keyboard; see '
            'http://goto/cros-canada')),
    Region('ca.multix', 'xkb:ca:multix:fra', 'America/Toronto', 'fr-CA',
           _KML.ISO, 'Canada (multilingual)',
           ('Device shipping to Canada with a Canadian Multilingual keyboard; '
            'see http://goto/cros-canada')),
    Region('de', 'xkb:de::ger', 'Europe/Berlin', 'de', _KML.ISO, 'Germany'),
    Region('fi', 'xkb:fi::fin', 'Europe/Helsinki', 'fi', _KML.ISO, 'Finland'),
    Region('fr', 'xkb:fr::fra', 'Europe/Paris', 'fr', _KML.ISO, 'France'),
    Region('gb', 'xkb:gb:extd:eng', 'Europe/London', 'en-GB', _KML.ISO, 'UK'),
    Region('ie', 'xkb:gb:extd:eng', 'Europe/Dublin', 'en-GB', _KML.ISO,
           'Ireland'),
    Region('in', 'xkb:us::eng', 'Asia/Calcutta', 'en-US', _KML.ANSI, 'India'),
    Region('my', 'xkb:us::eng', 'Asia/Kuala_Lumpur', 'ms', _KML.ANSI,
           'Malaysia'),
    Region('nl', 'xkb:us:intl:eng', 'Europe/Amsterdam', 'nl', _KML.ANSI,
           'Netherlands'),
    Region('nordic', 'xkb:se::swe', 'Europe/Stockholm', 'en-US', _KML.ISO,
           'Nordics', 'Unified keyboard for Sweden, Norway, and Denmark'),
    Region('se', 'xkb:se::swe', 'Europe/Stockholm', 'sv', _KML.ISO, 'Sweden'),
    Region('sg', 'xkb:us::eng', 'Asia/Singapore', 'en-GB', _KML.ANSI,
           'Singapore'),
    Region('us', 'xkb:us::eng', 'America/Los_Angeles', 'en-US', _KML.ANSI,
           'United States'),
]
"""A list of :py:class:`cros.factory.l10n.regions.Region` objects for
all **confirmed** regions.  A confirmed region is a region whose
properties are known to be correct and may be used to launch a device."""


UNCONFIRMED_REGIONS_LIST = []
"""A list of :py:class:`cros.factory.l10n.regions.Region` objects for
**unconfirmed** regions. These are believed to be correct but
unconfirmed, and all fields should be verified (and the row moved into
:py:data:`cros.factory.l10n.regions.Region.REGIONS_LIST`) before
launch. See <http://goto/vpdsettings>.

Currently, non-Latin keyboards must use an underlying Latin keyboard
for VPD. (This assumption should be revisited when moving items to
:py:data:`cros.factory.l10n.regions.Region.REGIONS_LIST`.)  This is
currently being discussed on <http://crbug.com/325389>.

Some timezones may be missing from ``timezone_settings.cc`` (see
http://crosbug.com/p/23902).  This must be rectified before moving
items to :py:data:`cros.factory.l10n.regions.Region.REGIONS_LIST`.
"""

INCOMPLETE_REGIONS_LIST = []
"""A list of :py:class:`cros.factory.l10n.regions.Region` objects for
**incomplete** regions.  These may contain incorrect information, and all
fields must be reviewed before launch. See http://goto/vpdsettings.
"""


def BuildRegionsDict(include_all=False):
  """Builds a dictionary mapping region code to
  :py:class:`py.l10n.regions.Region` object.

  The regions include:

  * :py:data:`cros.factory.l10n.regions.REGIONS_LIST`
  * :py:data:`cros.factory.l10n.regions_overlay.REGIONS_LIST`
  * Only if ``include_all`` is true:

    * :py:data:`cros.factory.l10n.regions.UNCONFIRMED_REGIONS_LIST`
    * :py:data:`cros.factory.l10n.regions_overlay.UNCONFIRMED_REGIONS_LIST`
    * :py:data:`cros.factory.l10n.regions.INCOMPLETE_REGIONS_LIST`
    * :py:data:`cros.factory.l10n.regions_overlay.INCOMPLETE_REGIONS_LIST`

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
