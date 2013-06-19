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
    Region('us', 'xkb:us::eng',     'America/Los_Angeles', 'en-US', _KML.ANSI),
    Region('gb', 'xkb:gb:extd:eng', 'Europe/London',       'en-GB', _KML.ISO),
]

# Attempt to read regions from the overlay.  No worries if they're not
# available.
try:
  from cros.factory.l10n import regions_overlay   # pylint: disable=E0611
  _REGIONS_LIST += regions_overlay.REGIONS_LIST
except ImportError:
  pass

REGIONS = dict((x.region_code, x) for x in _REGIONS_LIST)
