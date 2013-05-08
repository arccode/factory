# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory import cros_locale


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
  """
  def __init__(self, region_code, keyboard, time_zone, language_code):
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

_REGIONS_LIST = [
    Region('au', 'xkb:us::eng',     'Australia/Sydney',    'en-AU'),
    Region('ca', 'xkb:us::eng',     'America/New_York',    'en-CA'),
    Region('de', 'xkb:de::ger',     'Europe/Amsterdam',    'de'),
    Region('dk', 'xkb:dk::dan',     'Europe/Amsterdam',    'da'),
    Region('fi', 'xkb:fi::fin',     'Europe/Helsinki',     'fi'),
    Region('fr', 'xkb:fr::fra',     'Europe/Amsterdam',    'fr'),
    Region('gb', 'xkb:gb:extd:eng', 'Europe/London',       'en-GB'),
    Region('ie', 'xkb:gb:extd:eng', 'Europe/London',       'en-GB'),
    Region('it', 'xkb:it::ita',     'Europe/Amsterdam',    'it'),
    Region('jp', 'xkb:jp::jpn',     'Asia/Tokyo',          'ja'),
    Region('my', 'xkb:us::eng',     'Asia/Kuala_Lumpur',   'ms'),
    Region('nl', 'xkb:us:intl:eng', 'Europe/Amsterdam',    'nl'),
    Region('nz', 'xkb:us::eng',     'Pacific/Auckland',    'en-NZ'),
    Region('no', 'xkb:no::nob',     'Europe/Amsterdam',    'no'),
    Region('se', 'xkb:se::swe',     'Europe/Amsterdam',    'sv'),
    Region('sg', 'xkb:us::eng',     'Asia/Hong_Kong',      'en-GB'),
    Region('us', 'xkb:us::eng',     'America/Los_Angeles', 'en-US'),
]
REGIONS = dict((x.region_code, x) for x in _REGIONS_LIST)
