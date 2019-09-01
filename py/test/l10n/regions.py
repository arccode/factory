#!/usr/bin/env python2
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Authoritative source for factory region/locale configuration.

Run this module to display all known regions (use --help to see options).
"""


import argparse
import json
import os
import re
import subprocess
import sys

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils


KEYBOARD_PATTERN = re.compile(r'^xkb:\w+:[\w-]*:\w+$|'
                              r'^(ime|m17n|t13n):[\w:-]+$')
LANGUAGE_CODE_PATTERN = re.compile(r'^(\w+)(-[A-Z0-9]+)?$')

CROS_REGIONS_DATABASE_DEFAULT_PATH = '/usr/share/misc/cros-regions.json'
CROS_REGIONS_DATABASE_ENV_NAME = 'CROS_REGIONS_DATABASE'
CROS_REGIONS_DATABASE_GENERATOR_PATH = os.path.join(
    paths.FACTORY_DIR, '..', '..', 'platform2', 'regions', 'regions.py')

# crbug.com/624257: Only regions defined below can use be automatically
# populated for HWID field mappings in !region_field.
LEGACY_REGIONS_LIST = [
    'au', 'be', 'br', 'br.abnt', 'br.usintl', 'ca.ansi', 'ca.fr', 'ca.hybrid',
    'ca.hybridansi', 'ca.multix', 'ch', 'de', 'es', 'fi', 'fr', 'gb', 'ie',
    'in', 'it', 'latam-es-419', 'my', 'nl', 'nordic', 'nz', 'ph', 'ru', 'se',
    'sg', 'us', 'jp', 'za', 'ng', 'hk', 'gcc', 'cz', 'th', 'id', 'tw', 'pl',
    'gr', 'il', 'pt', 'ro', 'kr', 'ae', 'za.us', 'vn', 'at', 'sk', 'ch.usintl',
    'bd', 'bf', 'bg', 'ba', 'bb', 'wf', 'bl', 'bm', 'bn', 'bo', 'bh', 'bi',
    'bj', 'bt', 'jm', 'bw', 'ws', 'bq', 'bs', 'je', 'by', 'bz', 'rw', 'rs',
    'tl', 're', 'tm', 'tj', 'tk', 'gw', 'gu', 'gt', 'gs', 'gq', 'gp', 'gy',
    'gg', 'gf', 'ge', 'gd', 'ga', 'sv', 'gn', 'gm', 'gl', 'gi', 'gh', 'om',
    'tn', 'jo', 'hr', 'ht', 'hu', 'hn', 've', 'pr', 'ps', 'pw', 'sj', 'py',
    'iq', 'pa', 'pf', 'pg', 'pe', 'pk', 'pn', 'pm', 'zm', 'eh', 'ee', 'eg',
    'ec', 'sb', 'et', 'so', 'zw', 'sa', 'er', 'me', 'md', 'mg', 'mf', 'ma',
    'mc', 'uz', 'mm', 'ml', 'mo', 'mn', 'mh', 'mk', 'mu', 'mt', 'mw', 'mv',
    'mq', 'mp', 'ms', 'mr', 'im', 'ug', 'tz', 'mx', 'io', 'sh', 'fj', 'fk',
    'fm', 'fo', 'ni', 'no', 'na', 'vu', 'nc', 'ne', 'nf', 'np', 'nr', 'nu',
    'ck', 'ci', 'co', 'cn', 'cm', 'cl', 'cc', 'cg', 'cf', 'cd', 'cy', 'cx',
    'cr', 'cw', 'cv', 'cu', 'sz', 'sy', 'sx', 'kg', 'ke', 'ss', 'sr', 'ki',
    'kh', 'kn', 'km', 'st', 'si', 'kp', 'kw', 'sn', 'sm', 'sl', 'sc', 'kz',
    'ky', 'sd', 'do', 'dm', 'dj', 'dk', 'vg', 'ye', 'dz', 'uy', 'yt', 'um',
    'lb', 'lc', 'la', 'tv', 'tt', 'tr', 'lk', 'li', 'lv', 'to', 'lt', 'lu',
    'lr', 'ls', 'tf', 'tg', 'td', 'tc', 'ly', 'va', 'vc', 'ad', 'ag', 'af',
    'ai', 'vi', 'is', 'ir', 'am', 'al', 'ao', 'as', 'ar', 'aw', 'ax', 'az'
]


class RegionException(Exception):
  """Exception in Region handling."""
  pass


class Region(object):
  """Comprehensive, standard locale configuration per country/region.

  See :ref:`regions-values` for detailed information on how to set these values.
  """

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
  """A list of logical keyboard layout identifiers (e.g., ``xkb:us:intl:eng``
  or ``m17n:ar``).

  This was used for legacy VPD ``keyboard_layouts`` value."""

  time_zone = None
  """A `tz database time zone
  <http://en.wikipedia.org/wiki/List_of_tz_database_time_zones>`_
  identifier (e.g., ``America/Los_Angeles``). See
  `timezone_settings.cc <http://goo.gl/WSVUeE>`_ for supported time
  zones.

  This was used for legacy VPD ``initial_timezone`` value."""

  language_codes = None
  """A list of default language codes (e.g., ``en-US``); see
  `l10n_util.cc <http://goo.gl/kVkht>`_ for supported languages.

  This was used for legacy VPD ``initial_locale`` value."""

  keyboard_mechanical_layout = None
  """The keyboard's mechanical layout (``ANSI`` [US-like], ``ISO``
  [UK-like], ``JIS`` [Japanese], ``ABNT2`` [Brazilian] or ``KS`` [Korean])."""

  description = None
  """A human-readable description of the region.
  This defaults to :py:attr:`region_code` if not set."""

  notes = None
  """Notes about the region.  This may be None."""

  FIELDS = ['region_code', 'keyboards', 'time_zone', 'language_codes',
            'keyboard_mechanical_layout']
  """Names of fields that define the region."""

  def __init__(self, region_code, keyboards, time_zone, language_codes,
               keyboard_mechanical_layout, description=None, notes=None):
    """Constructor.

    Args:
      region_code: See :py:attr:`region_code`.
      keyboards: See :py:attr:`keyboards`.  A single string is accepted for
        backward compatibility.
      time_zone: See :py:attr:`time_zone`.
      language_codes: See :py:attr:`language_codes`.  A single string is
        accepted for backward compatibility.
      keyboard_mechanical_layout: See :py:attr:`keyboard_mechanical_layout`.
      description: See :py:attr:`description`.
      notes: See :py:attr:`notes`.
    """
    # Quick check: should be 'gb', not 'uk'
    if region_code == 'uk':
      raise RegionException("'uk' is not a valid region code (use 'gb')")

    self.region_code = region_code
    self.keyboards = type_utils.MakeList(keyboards)
    self.time_zone = time_zone
    self.language_codes = type_utils.MakeList(language_codes)
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
    return 'Region(%s)' % ', '.join(
        [repr(getattr(self, x)) for x in self.FIELDS])

  def __str__(self):
    return 'Region(%s)' % ', '.join([
        ';'.join(v) if isinstance(v, list) else str(v)
        for x in self.FIELDS for v in [getattr(self, x)]])

  def GetFieldsDict(self):
    """Returns a dict of all substantive fields.

    notes and description are excluded.
    """
    return dict((k, getattr(self, k)) for k in self.FIELDS)


def LoadRegionDatabaseFromSource():
  """Reads region database from a ChromiumOS source tree.

  This is required for unittest and the "make doc" commands.

  Returns: A json dictionary of region database.
  """
  # Try to load from source tree if available.
  src_root = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          '..', '..', '..', '..', '..')
  generator = os.path.join(src_root, 'platform2', 'regions', 'regions.py')
  if not os.path.exists(generator):
    return {}

  overlay_file = os.path.join(
      src_root, 'private-overlays', 'chromeos-partner-overlay',
      'chromeos-base', 'regions-private', 'files', 'regions_overlay.py')

  command = [generator, '--format=json', '--all', '--notes']
  if os.path.exists(overlay_file):
    command += ['--overlay=%s' % overlay_file]

  return json.loads(subprocess.check_output(command))


def LoadRegionDatabase(path=None):
  """Loads ChromeOS region database.

  Args:
    path: A string for path to regions database, or None to search for defaults.

  Returns a list of Regions as [confirmed, unconfirmed] .
  """
  def EncodeUnicode(value):
    if value is None:
      return None
    return ([s.encode('utf-8') for s in value] if isinstance(value, list) else
            value.encode('utf-8'))

  def FindDatabaseContents():
    """Finds database.

    Precedence:
     1. Path from environment variable (CROS_REGIONS_DATABASE_ENV_NAME).
     2. File in same folder where current module lives.
     3. File in sys.argv[0] (backward compatibility)
     4. Default file path (CROS_REGIONS_DATABASE_DEFAULT_PATH).

    Returns:
     Contents of database file.
    """
    path = os.getenv(CROS_REGIONS_DATABASE_ENV_NAME, None)
    if path:
      return file_utils.ReadFile(path)

    path = os.path.join(os.path.dirname(__file__),
                        os.path.basename(CROS_REGIONS_DATABASE_DEFAULT_PATH))
    data = file_utils.LoadModuleResource(path)
    if data is not None:
      return data

    path = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])),
                        os.path.basename(CROS_REGIONS_DATABASE_DEFAULT_PATH))
    if os.path.exists(path):
      return file_utils.ReadFile(path)

    if (sys_utils.InChroot() and
        os.path.isfile(CROS_REGIONS_DATABASE_GENERATOR_PATH)):
      return process_utils.CheckOutput(
          [CROS_REGIONS_DATABASE_GENERATOR_PATH, '--format', 'json', '--all'])

    path = CROS_REGIONS_DATABASE_DEFAULT_PATH
    if os.path.exists(path):
      return file_utils.ReadFile(path)

    return None

  confirmed = []
  unconfirmed = []

  if path:
    with open(path) as f:
      db = json.load(f)
  else:
    contents = FindDatabaseContents()
    if contents:
      db = json.loads(contents)
    else:
      db = LoadRegionDatabaseFromSource()

  for r in db.values():
    encoded = Region(EncodeUnicode(r['region_code']),
                     EncodeUnicode(r['keyboards']),
                     EncodeUnicode(r['time_zones'])[0],
                     EncodeUnicode(r['locales']),
                     EncodeUnicode(r['keyboard_mechanical_layout']),
                     EncodeUnicode(r['description']),
                     EncodeUnicode(r.get('notes')))
    if r.get('confirmed', True):
      confirmed.append(encoded)
    else:
      unconfirmed.append(encoded)
  return [confirmed, unconfirmed]


REGIONS_LIST = []
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


REGIONS = {}
"""A dict maps the region code to the
:py:class:`cros.factory.l10n.regions.Region` object."""


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
            'Conflicting definitions for region %r: %r, %r' %
            (r.region_code, existing_region.GetFieldsDict(),
             r.GetFieldsDict()))
    else:
      region_dict[r.region_code] = r

  return region_dict


def BuildRegionsDict(include_all=False):
  """Builds a dictionary mapping region code to
  :py:class:`py.l10n.regions.Region` object.

  The regions include:

  * :py:data:`cros.factory.l10n.regions.REGIONS_LIST`
  * Only if ``include_all`` is true:

    * :py:data:`cros.factory.l10n.regions.UNCONFIRMED_REGIONS_LIST`

  A region may only appear in one of the above lists, or this function
  will (deliberately) fail.
  """
  regions = list(REGIONS_LIST)
  if include_all:
    regions += UNCONFIRMED_REGIONS_LIST

  # Build dictionary of region code to list of regions with that
  # region code.  Check manually for duplicates, since the region may
  # be present both in the overlay and the public repo.
  return _ConsolidateRegions(regions)


def InitialSetup(region_database_path=None, include_all=False):
  # pylint: disable=global-statement
  global REGIONS_LIST, UNCONFIRMED_REGIONS_LIST, REGIONS

  REGIONS_LIST, UNCONFIRMED_REGIONS_LIST = LoadRegionDatabase(
      path=region_database_path)
  REGIONS = BuildRegionsDict(include_all=include_all)


InitialSetup()


def main(args=sys.argv[1:], out=sys.stdout):
  parser = argparse.ArgumentParser(description=(
      'Display all known regions and their parameters. '))
  parser.add_argument('--format', choices=('human-readable', 'csv'),
                      default='human-readable',
                      help='Output format (default=%(default)s)')
  parser.add_argument('--all', action='store_true',
                      help='Include unconfirmed and incomplete regions')
  args = parser.parse_args(args)

  regions_dict = BuildRegionsDict(include_all=args.all)

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
