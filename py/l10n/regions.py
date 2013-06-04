# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory import cros_locale
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
      http://goo.gl/3aJnl.
    time_zone: The standard time zone (e.g., 'America/Los_Angeles'); see
      http://goo.gl/IqLVX.
    language code: The standard language code (e.g., 'en-US'); see
      http://goo.gl/kVkht.
    keyboard_mechanical_layout: The keyboard's mechanical layout (ANSI
      [US-like], ISO [UK-like], or JIS).
  """
  def __init__(self, region_code, keyboard, time_zone, language_code,
               keyboard_mechanical_layout):
    assert region_code != 'uk'
    assert keyboard in cros_locale.ALL_KEYBOARDS, '%s not in %s' % (
        keyboard, cros_locale.ALL_KEYBOARDS)
    assert time_zone in cros_locale.CHROMEOS_TIMEZONE_LIST, '%s not in %s' % (
        time_zone, cros_locale.CHROMEOS_TIMEZONE_LIST)
    assert language_code in cros_locale.CHROMEOS_LOCALE_DATABASE, (
        '%s not in %s' % (language_code, cros_locale.CHROMEOS_LOCALE_DATABASE))

    self.region_code = region_code
    self.keyboard = keyboard
    self.time_zone = time_zone
    self.language_code = language_code
    self.keyboard_mechanical_layout = keyboard_mechanical_layout

_KML = KeyboardMechanicalLayout
_REGIONS_LIST = [
    Region('au', 'xkb:us::eng',     'Australia/Sydney',    'en-AU', _KML.ANSI),
    Region('ca', 'xkb:us::eng',     'America/New_York',    'en-CA', _KML.ANSI),
    Region('de', 'xkb:de::ger',     'Europe/Amsterdam',    'de',    _KML.ISO),
    Region('dk', 'xkb:dk::dan',     'Europe/Amsterdam',    'da',    _KML.ISO),
    Region('fi', 'xkb:fi::fin',     'Europe/Helsinki',     'fi',    _KML.ISO),
    Region('fr', 'xkb:fr::fra',     'Europe/Amsterdam',    'fr',    _KML.ISO),
    Region('gb', 'xkb:gb:extd:eng', 'Europe/London',       'en-GB', _KML.ISO),
    Region('ie', 'xkb:gb:extd:eng', 'Europe/London',       'en-GB', _KML.ISO),
    Region('it', 'xkb:it::ita',     'Europe/Amsterdam',    'it',    _KML.ISO),
    Region('jp', 'xkb:jp::jpn',     'Asia/Tokyo',          'ja',    _KML.JIS),
    Region('my', 'xkb:us::eng',     'Asia/Kuala_Lumpur',   'ms',    _KML.ANSI),
    Region('nl', 'xkb:us:intl:eng', 'Europe/Amsterdam',    'nl',    _KML.ANSI),
    Region('nz', 'xkb:us::eng',     'Pacific/Auckland',    'en-NZ', _KML.ANSI),
    Region('no', 'xkb:no::nob',     'Europe/Amsterdam',    'no',    _KML.ISO),
    Region('se', 'xkb:se::swe',     'Europe/Amsterdam',    'sv',    _KML.ISO),
    Region('sg', 'xkb:us::eng',     'Asia/Hong_Kong',      'en-GB', _KML.ANSI),
    Region('us', 'xkb:us::eng',     'America/Los_Angeles', 'en-US', _KML.ANSI),
]
REGIONS = dict((x.region_code, x) for x in _REGIONS_LIST)
