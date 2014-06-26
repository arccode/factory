#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Authoritative source for factory region/locale configuration.

Run this module to display all known regions (use --help to see options).
"""


import argparse
import re
import sys
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory import common
from cros.factory.test.utils import Enum


# ANSI = US-like
# ISO = UK-like
# JIS = Japanese
# ABNT2 = Brazilian (like ISO but with an extra key to the left of the
#   right shift key)
KeyboardMechanicalLayout = Enum(['ANSI', 'ISO', 'JIS', 'ABNT2'])


KEYBOARD_PATTERN = re.compile(r'^xkb:\w+:\w*:\w+$')
LANGUAGE_CODE_PATTERN = re.compile(r'^(\w+)(-[A-Z0-9]+)?$')


class RegionException(Exception):
  """Exception in Region handling."""
  pass


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

  keyboards = None
  """A list of XKB keyboard layout identifiers (e.g.,
  ``xkb:us:intl:eng``); see `input_method_util.cc
  <http://goo.gl/cDO53r>`_ and `input_methods.txt
  <http://goo.gl/xWNrUP>`_ for supported keyboards.  Note that the
  keyboard must be whitelisted for login, i.e., the respective line in
  `input_methods.txt <http://goo.gl/xWNrUP>`_ must contain the
  ``login`` keyword.

  This is used to set the VPD ``keyboard_layout`` value."""

  @property
  def keyboard(self):
    """The first item in the 'keyboards' array, for backward compatibility.

    Deprecated; use :py:attr:`keyboards` instead.
    """
    return self.keyboards[0]

  time_zone = None
  """A `tz database time zone
  <http://en.wikipedia.org/wiki/List_of_tz_database_time_zones>`_
  identifier (e.g., ``America/Los_Angeles``). See
  `timezone_settings.cc <http://goo.gl/WSVUeE>`_ for supported time
  zones.

  This is used to set the VPD ``initial_timezone`` value."""

  language_codes = None
  """A list of default language codes (e.g., ``en-US``); see
  `l10n_util.cc <http://goo.gl/kVkht>`_ for supported languages.

  This is used to set the VPD ``initial_locale`` language."""

  @property
  def language_code(self):
    """The first item in the language_codes list, for backward compatibility.

    Deprecated; use :py:attr:`language_codes` instead.
    """
    return self.language_codes[0]

  keyboard_mechanical_layout = None
  """The keyboard's mechanical layout (``ANSI`` [US-like], ``ISO``
  [UK-like], ``JIS`` [Japanese], or ``ABNT2`` [Brazilian])."""

  description = None
  """A human-readable description of the region.
  This defaults to :py:attr:`region_code` if not set."""

  notes = None
  """Notes about the region.  This may be None."""

  FIELDS = ['region_code', 'keyboards', 'time_zone', 'language_codes',
            'keyboard_mechanical_layout']
  """Names of fields that define the region."""

  """Constructor.

  Args:
    region_code: See :py:attr:`region_code`.
    keyboards: See :py:attr:`keyboards`.  A single string is accepted for
      backward compatibility.
    time_zone: See :py:attr:`time_zone`.
    language_codes: See :py:attr:`language_codes`.  A single string is accepted
      for backward compatibility.
  """
  def __init__(self, region_code, keyboards, time_zone, language_codes,
               keyboard_mechanical_layout, description=None, notes=None):
    # Quick check: should be 'gb', not 'uk'
    if region_code == 'uk':
      raise RegionException("'uk' is not a valid region code (use 'gb')")

    self.region_code = region_code
    self.keyboards = common.MakeList(keyboards)
    self.time_zone = time_zone
    self.language_codes = common.MakeList(language_codes)
    self.keyboard_mechanical_layout = keyboard_mechanical_layout
    self.description = description or region_code
    self.notes = notes

    for f in (self.keyboards, self.language_codes):
      assert all(isinstance(x, str) for x in f), (
          'Expected a list of strings, not %r' % f)
    for f in self.keyboards:
      assert KEYBOARD_PATTERN.match(f), (
          'Keyboard pattern %r does not match %r' % (
              f, KEYBOARD_PATTERN.pattern))
    for f in self.language_codes:
      assert LANGUAGE_CODE_PATTERN.match(f), (
          'Language code %r does not match %r' % (
              f, LANGUAGE_CODE_PATTERN.pattern))

  def __repr__(self):
    return 'Region(%s)' % (', '.join([getattr(self, x) for x in self.FIELDS]))

  def GetFieldsDict(self):
    """Returns a dict of all substantive fields.

    notes and description are excluded.
    """
    return dict((k, getattr(self, k)) for k in self.FIELDS)

  def GetVPDSettings(self, allow_multiple=True):
    """Returns a dictionary of VPD settings for the locale.

    Args:
      allow_multiple: Allow multiple initial_locale and initial_timezone values
        (supported only in M34+).
    """
    if allow_multiple:
      initial_locale = ','.join(self.language_codes)
      keyboard = ','.join(self.keyboards)
    else:
      initial_locale = self.language_codes[0]
      keyboard = self.keyboards[0]

    return dict(initial_locale=initial_locale,
                keyboard_layout=keyboard,
                initial_timezone=self.time_zone,
                region=self.region_code)

_KML = KeyboardMechanicalLayout
REGIONS_LIST = [
    Region('au', 'xkb:us::eng', 'Australia/Sydney', 'en-AU', _KML.ANSI,
           'Australia'),
    Region('be', 'xkb:be::nld', 'Europe/Brussels', 'en-GB', _KML.ISO, 'Belgium',
           'Flemish (Belgian Dutch) keyboard; British English language for '
           'neutrality'),
    Region('br', 'xkb:br::por', 'America/Sao_Paulo', 'pt-BR', _KML.ABNT2,
           'Brazil (ABNT2)',
           ('ABNT2 = ABNT NBR 10346 variant 2. This is the preferred layout '
            'for Brazil. ABNT2 is mostly an ISO layout, but it has an extra '
            'key to the left of the right shift key; see '
            'http://goo.gl/twA5tq')),
    Region('br.abnt', 'xkb:br::por', 'America/Sao_Paulo', 'pt-BR', _KML.ISO,
           'Brazil (ABNT)',
           ('Like ABNT2, but lacking the extra key to the left of the right '
            'shift key found in that layout. ABNT2 (the "br" region) is '
            'preferred to this layout')),
    Region('br.usintl', 'xkb:us:intl:eng', 'America/Sao_Paulo', 'pt-BR',
           _KML.ANSI, 'Brazil (US Intl)',
           'Brazil with US International keyboard layout. ABNT2 ("br") and '
           'ABNT1 ("br.abnt1 ") are both preferred to this.'),
    Region('ca.ansi', 'xkb:us::eng', 'America/Toronto', 'en-CA', _KML.ANSI,
           'Canada (US keyboard)',
           'Canada with US (ANSI) keyboard. Not for en/fr hybrid ANSI '
           'keyboards; for that you would want ca.hybridansi. See '
           'http://goto/cros-canada'),
    Region('ca.fr', 'xkb:ca::fra', 'America/Toronto', 'fr-CA', _KML.ISO,
           'Canada (French keyboard)',
           ('Canadian French (ISO) keyboard. The most common configuration for '
            'Canadian French SKUs.  See http://goto/cros-canada')),
    Region('ca.hybrid', 'xkb:ca:eng:eng', 'America/Toronto', 'en-CA', _KML.ISO,
           'Canada (hybrid ISO)',
           ('Canada with hybrid (ISO) xkb:ca:eng:eng + xkb:ca::fra keyboard, '
            'defaulting to English language and keyboard.  Used only if there '
            'needs to be a single SKU for all of Canada.  See '
            'http://goto/cros-canada')),
    Region('ca.hybridansi', 'xkb:ca:eng:eng', 'America/Toronto', 'en-CA',
           _KML.ANSI, 'Canada (hybrid ANSI)',
           ('Canada with hybrid (ANSI) xkb:ca:eng:eng + xkb:ca::fra keyboard, '
            'defaulting to English language and keyboard.  Used only if there '
            'needs to be a single SKU for all of Canada.  See '
            'http://goto/cros-canada')),
    Region('ca.multix', 'xkb:ca:multix:fra', 'America/Toronto', 'fr-CA',
           _KML.ISO, 'Canada (multilingual)',
           ("Canadian Multilingual keyboard; you probably don't want this. See "
            "http://goto/cros-canada")),
    Region('ch', 'xkb:ch::ger', 'Europe/Zurich', 'en-US', _KML.ISO,
           'Switzerland',
           'German keyboard, but US English to be language-neutral; used in '
           'the common case that there is only a single Swiss SKU.'),
    Region('de', 'xkb:de::ger', 'Europe/Berlin', 'de', _KML.ISO, 'Germany'),
    Region('es', 'xkb:es::spa', 'Europe/Madrid', 'es', _KML.ISO, 'Spain'),
    Region('fi', 'xkb:fi::fin', 'Europe/Helsinki', 'fi', _KML.ISO, 'Finland'),
    Region('fr', 'xkb:fr::fra', 'Europe/Paris', 'fr', _KML.ISO, 'France'),
    Region('gb', 'xkb:gb:extd:eng', 'Europe/London', 'en-GB', _KML.ISO, 'UK'),
    Region('ie', 'xkb:gb:extd:eng', 'Europe/Dublin', 'en-GB', _KML.ISO,
           'Ireland'),
    Region('in', 'xkb:us::eng', 'Asia/Calcutta', 'en-US', _KML.ANSI, 'India'),
    Region('it', 'xkb:it::ita', 'Europe/Rome', 'it', _KML.ISO, 'Italy'),
    Region('latam-es-419', 'xkb:es::spa', 'America/Mexico_City', 'es-419',
           _KML.ISO, 'Hispanophone Latin America',
           ('Spanish-speaking countries in Latin America, using the Iberian '
            '(Spain) Spanish keyboard, which is increasingly dominant in '
            'Latin America. Known to be correct for '
            'Chile, Colombia, Mexico, Peru; '
            'still unconfirmed for other es-419 countries. The old Latin '
            'American layout (xkb:latam::spa) has not been approved; before '
            'using that you must seek review through http://goto/vpdsettings. '
            'See also http://goo.gl/Iffuqh. Note that 419 is the UN M.49 '
            'region code for Latin America')),
    Region('my', 'xkb:us::eng', 'Asia/Kuala_Lumpur', 'ms', _KML.ANSI,
           'Malaysia'),
    Region('nl', 'xkb:us:intl:eng', 'Europe/Amsterdam', 'nl', _KML.ANSI,
           'Netherlands'),
    Region('nordic', 'xkb:se::swe', 'Europe/Stockholm', 'en-US', _KML.ISO,
           'Nordics',
           ('Unified SKU for Sweden, Norway, and Denmark.  This defaults '
            'to Swedish keyboard layout, but starts with US English language '
            'for neutrality.  Use if there is a single combined SKU for Nordic '
            'countries.')),
    Region('nz', 'xkb:us::eng', 'Pacific/Auckland', 'en-NZ', _KML.ANSI,
           'New Zealand'),
    Region('ph', 'xkb:us::eng', 'Asia/Manila', 'en-US', _KML.ANSI,
           'Philippines'),
    Region('ru', 'xkb:ru::rus', 'Europe/Moscow', 'ru', _KML.ANSI, 'Russia',
           'For R31+ only; R30 and earlier must use US keyboard for login'),
    Region('se', 'xkb:se::swe', 'Europe/Stockholm', 'sv', _KML.ISO, 'Sweden',
           ("Use this if there separate SKUs for Nordic countries (Sweden, "
            "Norway, and Denmark), or the device is only shipping to Sweden. "
            "If there is a single unified SKU, use 'nordic' instead.")),
    Region('sg', 'xkb:us::eng', 'Asia/Singapore', 'en-GB', _KML.ANSI,
           'Singapore'),
    Region('us', 'xkb:us::eng', 'America/Los_Angeles', 'en-US', _KML.ANSI,
           'United States'),
]
"""A list of :py:class:`cros.factory.l10n.regions.Region` objects for
all **confirmed** regions.  A confirmed region is a region whose
properties are known to be correct and may be used to launch a device."""


UNCONFIRMED_REGIONS_LIST = [
    Region('jp', 'xkb:jp::jpn', 'Asia/Tokyo', 'ja', _KML.JIS, 'Japan'),
]
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


def _ConsolidateRegions(regions):
  """Consolidates a list of regions into a dict.

  Args:
    regions: A list of Region objects.  All objects for any given
      region code must be identical or we will throw an exception.
      (We allow duplicates in case identical region objects are
      defined in both regions.py and the overlay, e.g., when moving
      items to the public overlay.)

  Returns:
    A dict from region code to Region.

  Raises:
    RegionException: If there are multiple regions defined for a given
      region, and the values for those regions differ.
  """
  # Build a dict from region_code to the first Region with that code.
  region_dict = {}
  for r in regions:
    existing_region = region_dict.get(r.region_code)
    if existing_region:
      if existing_region.GetFieldsDict() != r.GetFieldsDict():
        raise RegionException(
          "Conflicting definitions for region %r: %r, %r" % (
            r.region_code, existing_region.GetFieldsDict(), r.GetFieldsDict()))
    else:
      region_dict[r.region_code] = r

  return region_dict

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

  # Build dictionary of region code to list of regions with that
  # region code.  Check manually for duplicates, since the region may
  # be present both in the overlay and the public repo.
  return _ConsolidateRegions(regions)


REGIONS = BuildRegionsDict()


def main(args=sys.argv[1:], out=sys.stdout):
  parser = argparse.ArgumentParser(description=(
      'Display all known regions and their parameters. '
      'To include any regions in the board overlay, run '
      '"make overlay-$BOARD && overlay-$BOARD/py/l10n/regions.py" '
      'from the platform/factory directory.'))
  parser.add_argument('--format', choices=('human-readable', 'csv', 'yaml'),
                      default='human-readable',
                      help='Output format (default=%(default)s)')
  parser.add_argument('--all', action='store_true',
                      help='Include unconfirmed and incomplete regions')
  args = parser.parse_args(args)

  regions_dict = BuildRegionsDict(args.all)

  # Handle YAML output.
  if args.format == 'yaml':
    data = {}
    for region in regions_dict.values():
      item = dict(vpd_settings=region.GetVPDSettings())
      for field in Region.FIELDS:
        item[field] = getattr(region, field)
      data[region.region_code] = item
    yaml.dump(data, out)
    return

  # Handle CSV or plain-text output: build a list of lines to print.
  lines = [Region.FIELDS]
  def CoerceToString(value):
    """If value is a list, concatenate its values with commas.
    Otherwise, just return value.
    """
    if isinstance(value, list):
      return ','.join(value)
    else:
      return str(value)
  for region in sorted(regions_dict.values(), key=lambda v: v.region_code):
    lines.append([CoerceToString(getattr(region, field))
                  for field in Region.FIELDS])

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
        out.write(line[column_no].ljust(max_lengths[column_no] + 2))
      out.write('\n')


if __name__ == '__main__':
  main()
