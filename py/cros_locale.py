# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=C0301

# References
# - Keyboard: http://gerrit.chromium.org/gerrit/gitweb?p=chromium/src.git;a=blob;f=chrome/browser/chromeos/input_method/ibus_input_methods.txt
# - Locale: http://git.chromium.org/gitweb/?p=chromium.git;a=blob;f=ui/base/l10n/l10n_util.cc
# - Time Zone: http://git.chromium.org/gitweb/?p=chromium.git;a=blob;f=chrome/browser/chromeos/dom_ui/system_settings_provider.cc
#              http://google.com/codesearch/p?#uX1GffpyOZk/core/tests/coretests/src/android/util/TimeUtilsTest.java
#              http://en.wikipedia.org/wiki/List_of_time_zones_by_UTC_offset

# This is the mapping from locale code to human readable locale name and
# suggested timezone.
# TODO(hungte) Some locales do not have default time zone yet.

CHROMEOS_LOCALE_DATABASE = {
    'af': ('Afrikaans', ''),
    'am': ('Amharic', ''),
    'ar': ('Arabic', ''),
    'az': ('Azerbaijani', ''),
    'be': ('Belarusian', ''),
    'bg': ('Bulgarian (Bulgaria)', 'Europe/Sofia'),
    'bh': ('Bihari', ''),
    'bn': ('Bengali', ''),
    'br': ('Breton', ''),
    'bs': ('Bosnian', ''),
    'ca': ('Catalan', ''),
    'co': ('Corsican', ''),
    'cs': ('Czech (Czech Republic)', 'Europe/Prague'),
    'cy': ('Welsh', ''),
    'da': ('Danish (Denmark)', 'Europe/Copenhagen'),
    'de': ('German (Germany)', 'Europe/Berlin'),
    'de-AT': ('German (Austria)', 'Europe/Vienna'),
    'de-CH': ('German (Switzerland)', 'Europe/Zurich'),
    'de-DE': ('German (Germany)', 'Europe/Berlin'),
    'el': ('Greek (Greece)', 'Europe/Athens'),
    'en': ('English (US)', 'America/Los_Angeles'),
    'en-AU': ('English (Austrailia)', 'Australia/Sydney'),
    'en-CA': ('English (Canada)', 'America/Toronto'),
    'en-GB': ('English (United Kingdom)', 'Europe/London'),
    'en-NZ': ('English (New Zealand)', ''),
    'en-US': ('English (US)', 'America/Los_Angeles'),
    'en-ZA': ('English (South Africa)', ''),
    'eo': ('Esperanto', ''),
    'es': ('Spanish (Spain)', 'Europe/Madrid'),
    'es-419': ('Spanish (Latin America)', 'America/Argentina/Buenos_Aires'),
    'et': ('Estonian (Estonia)', 'Europe/Tallinn'),
    'eu': ('Basque', ''),
    'fa': ('Persian', ''),
    'fi': ('Finnish (Finland)', 'Europe/Helsinki'),
    'fil': ('Filipino', ''),
    'fo': ('Faroese', ''),
    'fr': ('French (France)', 'Europe/Paris'),
    'fr-CA': ('French (Canada)', 'America/Toronto'),
    'fr-CH': ('French (Switzerland)', 'Europe/Zurich'),
    'fr-FR': ('French (France)', 'Europe/Paris'),
    'fy': ('Frisian', ''),
    'ga': ('Irish', ''),
    'gd': ('Scots Gaelic', ''),
    'gl': ('Galician', ''),
    'gn': ('Guarani', ''),
    'gu': ('Gujarati', ''),
    'ha': ('Hausa', ''),
    'haw': ('Hawaiian', ''),
    'he': ('Hebrew (Israel)', 'Asia/Jerusalem'),
    'hi': ('Hindi', ''),
    'hr': ('Croatian (Croatia)', 'Europe/Zagreb'),
    'hu': ('Hungarian (Hungary)', 'Europe/Budapest'),
    'hy': ('Armenian', ''),
    'ia': ('Interlingua', ''),
    'id': ('Indonesian', ''),
    'is': ('Icelandic', ''),
    'it': ('Italian', 'Europe/Rome'),
    'it-CH': ('Italian (Switzerland)', 'Europe/Zurich'),
    'it-IT': ('Italian (Italy)', 'Europe/Rome'),
    'ja': ('Japanese (Japan)', 'Asia/Tokyo'),
    'jw': ('Javanese', ''),
    'ka': ('Georgian', ''),
    'kk': ('Kazakh', ''),
    'km': ('Cambodian', ''),
    'kn': ('Kannada', ''),
    'ko': ('Korean (Korea)', 'Asia/Seoul'),
    'ku': ('Kurdish', ''),
    'ky': ('Kyrgyz', ''),
    'la': ('Latin', ''),
    'ln': ('Lingala', ''),
    'lo': ('Laothian', ''),
    'lt': ('Lithuanian (Lithuania)', 'Europe/Vilnius'),
    'lv': ('Latvian (Latvia)', 'Europe/Riga'),
    'mk': ('Macedonian', ''),
    'ml': ('Malayalam', ''),
    'mn': ('Mongolian', ''),
    'mo': ('Moldavian', ''),
    'mr': ('Marathi', ''),
    'ms': ('Malay', ''),
    'mt': ('Maltese', ''),
    'nb': ('Norwegian (Bokmal)', 'Europe/Oslo'),
    'ne': ('Nepali', ''),
    'nl': ('Dutch (Netherlands)', 'Europe/Amsterdam'),
    'nn': ('Norwegian (Nynorsk)', ''),
    'no': ('Norwegian (Norway)', 'Europe/Oslo'),
    'oc': ('Occitan', ''),
    'om': ('Oromo', ''),
    'or': ('Oriya', ''),
    'pa': ('Punjabi', ''),
    'pl': ('Polish (Poland)', 'Europe/Warsaw'),
    'ps': ('Pashto', ''),
    'pt': ('Portuguese', ''),
    'pt-BR': ('Portuguese (Brazil)', 'America/Sao_Paulo'),
    'pt-PT': ('Portuguese (Portugal)', 'Europe/Lisbon'),
    'qu': ('Quechua', ''),
    'rm': ('Romansh', ''),
    'ro': ('Romanian (Romania)', 'Europe/Bucharest'),
    'ru': ('Russian (Russia)', 'Europe/Moscow'),
    'sd': ('Sindhi', ''),
    'sh': ('Serbo-Croatian', ''),
    'si': ('Sinhalese', ''),
    'sk': ('Slovak (Slovakia)', 'Europe/Bratislava'),
    'sl': ('Slovenian (Slovenia)', 'Europe/Ljubljana'),
    'sn': ('Shona', ''),
    'so': ('Somali', ''),
    'sq': ('Albanian', ''),
    'sr': ('Serbian (Serbia)', 'Europe/Belgrade'),
    'st': ('Sesotho', ''),
    'su': ('Sundanese', ''),
    'sv': ('Swedish (Sweden)', 'Europe/Stockholm'),
    'sw': ('Swahili', ''),
    'ta': ('Tamil', ''),
    'te': ('Telugu', ''),
    'tg': ('Tajik', ''),
    'th': ('Thai', ''),
    'ti': ('Tigrinya', ''),
    'tk': ('Turkmen', ''),
    'to': ('Tonga', ''),
    'tr': ('Turkish (Turkey)', 'Europe/Istanbul'),
    'tt': ('Tatar', ''),
    'tw': ('Twi', ''),
    'ug': ('Uighur', ''),
    'uk': ('Ukrainian (Ukraine)', 'Europe/Kiev'),
    'ur': ('Urdu', ''),
    'uz': ('Uzbek', ''),
    'vi': ('Vietnamese', ''),
    'xh': ('Xhosa', ''),
    'yi': ('Yiddish', ''),
    'yo': ('Yoruba', ''),
    'zh': ('Chinese', ''),
    'zh-CN': ('Chinese (China)', 'Asia/Shanghai'),
    'zh-TW': ('Chinese (Taiwan)', 'Asia/Taipei'),
    'zu': ('Zulu', ''),
}

# Approved timezone names in ChromeOS. Any unlisted names must be remapped in #
# UNSUPPORTED_TIMEZONE_MAP.
CHROMEOS_TIMEZONE_LIST = [
    "Pacific/Majuro",
    "Pacific/Midway",
    "Pacific/Honolulu",
    "America/Anchorage",
    "America/Los_Angeles",
    "America/Tijuana",
    "America/Denver",
    "America/Phoenix",
    "America/Chihuahua",
    "America/Chicago",
    "America/Mexico_City",
    "America/Costa_Rica",
    "America/Regina",
    "America/New_York",
    "America/Bogota",
    "America/Caracas",
    "America/Barbados",
    "America/Manaus",
    "America/Santiago",
    "America/St_Johns",
    "America/Sao_Paulo",
    "America/Araguaina",
    "America/Argentina/Buenos_Aires",
    "America/Godthab",
    "America/Montevideo",
    "Atlantic/South_Georgia",
    "Atlantic/Azores",
    "Atlantic/Cape_Verde",
    "Africa/Casablanca",
    "Europe/London",
    "Europe/Amsterdam",
    "Europe/Belgrade",
    "Europe/Brussels",
    "Europe/Sarajevo",
    "Africa/Windhoek",
    "Africa/Brazzaville",
    "Asia/Amman",
    "Europe/Athens",
    "Asia/Beirut",
    "Africa/Cairo",
    "Europe/Helsinki",
    "Asia/Jerusalem",
    "Europe/Minsk",
    "Africa/Harare",
    "Asia/Baghdad",
    "Europe/Moscow",
    "Asia/Kuwait",
    "Africa/Nairobi",
    "Asia/Tehran",
    "Asia/Baku",
    "Asia/Tbilisi",
    "Asia/Yerevan",
    "Asia/Dubai",
    "Asia/Kabul",
    "Asia/Karachi",
    "Asia/Oral",
    "Asia/Yekaterinburg",
    "Asia/Calcutta",
    "Asia/Colombo",
    "Asia/Katmandu",
    "Asia/Almaty",
    "Asia/Rangoon",
    "Asia/Krasnoyarsk",
    "Asia/Bangkok",
    "Asia/Shanghai",
    "Asia/Hong_Kong",
    "Asia/Irkutsk",
    "Asia/Kuala_Lumpur",
    "Australia/Perth",
    "Asia/Taipei",
    "Asia/Seoul",
    "Asia/Tokyo",
    "Asia/Yakutsk",
    "Australia/Adelaide",
    "Australia/Darwin",
    "Australia/Brisbane",
    "Australia/Hobart",
    "Australia/Sydney",
    "Asia/Vladivostok",
    "Pacific/Guam",
    "Asia/Magadan",
    "Pacific/Auckland",
    "Pacific/Fiji",
    "Pacific/Tongatapu",
]

# Lots of time zones are currently not supported in ChromeOS;
# and here is a map for equivalent time zones.
UNSUPPORTED_TIMEZONE_MAP = {
    'Africa/Addis_Ababa': 'UTC+3',
    'America/Paramaribo': 'UTC-3',
    'America/Toronto': 'UTC-5',
    'Europe/Belgrade': 'UTC+1',
    'Europe/Berlin': 'UTC+1',
    'Europe/Bratislava': 'UTC+1',
    'Europe/Bucharest': 'UTC+2',
    'Europe/Budapest': 'UTC+1',
    'Europe/Copenhagen': 'UTC+1',
    'Europe/Istanbul': 'UTC+2',
    'Europe/Kiev': 'UTC+2',
    'Europe/Lisbon': 'UTC+0',
    'Europe/Ljubljana': 'UTC+1',
    'Europe/Madrid': 'UTC+1',
    'Europe/Oslo': 'UTC+1',
    'Europe/Paris': 'UTC+1',
    'Europe/Prague': 'UTC+1',
    'Europe/Riga': 'UTC+2',
    'Europe/Rome': 'UTC+1',
    'Europe/Sofia': 'UTC+2',
    'Europe/Stockholm': 'UTC+1',
    'Europe/Tallinn': 'UTC+2',
    'Europe/Vienna': 'UTC+1',
    'Europe/Vilnius': 'UTC+2',
    'Europe/Warsaw': 'UTC+1',
    'Europe/Zagreb': 'UTC+1',
    'Europe/Zurich': 'UTC+1',
    'UTC-5': 'America/New_York',
    'UTC-3': 'America/Argentina/Buenos_Aires',
    'UTC+0': 'Europe/London',
    'UTC+1': 'Europe/Amsterdam',
    'UTC+2': 'Europe/Athens',
    'UTC+3': 'Africa/Nairobi',
}


# Default list of valid region information.
# Syntax: (initial_locale, keyboard_layout, timezone, description)
#  timezone and description are optional fields.
#  If description is None, derive from CHROMEOS_LOCALE_DATABASE
#  If description starts with '+', concatenate with the derived string
#  If timezone is None, derive from CHROMEOS_LOCALE_DATABASE
DEFAULT_REGION_LIST = (
    # Common regions
    (None, ),
    ('en-US', 'xkb:us::eng',),
    ('en-GB', 'xkb:gb:extd:eng',),
    ('fr',    'xkb:fr::fra',),
    ('de',    'xkb:de::ger',),
    ('en-US', 'xkb:us:intl:eng', None, '+(International)'),

    # Other regions.
    ('bg',    'xkb:bg::bul',),
    ('bg',    'xkb:bg:phonetic:bul', None, '+(Phonetic)'),
    ('en-CA', 'xkb:ca:eng:eng',),
    ('fr-CA', 'xkb:ca::fra',),
    ('de-CH', 'xkb:ch::ger',),
    ('fr-CH', 'xkb:ch:fr:fra',),
    ('cs',    'xkb:cz::cze',),
    ('da',    'xkb:dk::dan',),
    ('de',    'xkb:de:neo:ger', None, '+(Neo 2)'),
    ('el',    'xkb:gr::gre',),
    ('en-AU', 'xkb:us::eng',),
    ('en-GB', 'xkb:gb:dvorak:eng', None, '+(Dvorak)'),
    ('en-US', 'xkb:us:altgr-intl:eng',None, '+ Extended (AltGr)'),
    ('en-US', 'xkb:us:colemak:eng', None, '+(Colemak)'),
    ('en-US', 'xkb:us:dvorak:eng', None, '+(Dvorak)'),
    ('es',    'xkb:es::spa',),
    ('et',    'xkb:ee::est',),
    ('fi',    'xkb:fi::fin',),
    ('hr',    'xkb:hr::scr',),
    ('hu',    'xkb:hu::hun',),
    ('he',    'xkb:il::heb',),
    ('it',    'xkb:it::ita',),
    ('ja',    'xkb:jp::jpn',),
    ('ko',    'xkb:kr:kr104:kor', None, '+(101/104 key Compatible)'),
    ('lt',    'xkb:lt::lit',),
    ('lv',    'xkb:lv:apostrophe:lav',),
    ('nb',    'xkb:no::nob',),
    ('pl',    'xkb:pl::pol',),
    ('pt-BR', 'xkb:br::por',),
    ('pt-PT', 'xkb:pt::por',),
    ('ro',    'xkb:ro::rum',),
    ('ru',    'xkb:ru::rus',),
    ('ru',    'xkb:ru:phonetic:rus', None, '+(Phonetic)'),
    ('sk',    'xkb:sk::slo',),
    ('sl',    'xkb:si::slv',),
    ('sr',    'xkb:rs::srp',),
    ('sv',    'xkb:se::swe',),
    ('tr',    'xkb:tr::tur',),
    ('uk',    'xkb:ua::ukr',),

    # Buggy combination

    # Netherlands is known to use xkb:us:intl:eng more than xkb:nl:nld.
    # http://en.wikipedia.org/wiki/Keyboard_layout#Dutch_.28Netherlands.29
    ('nl',    'xkb:us:intl:eng', None, '+(US Layout)'),
    ('nl',    'xkb:nl::nld', None, '+(w/guldenteken, deprecated)'),

    # TODO(hungte) Belgium should be nl-BE, de-BE, fr-BE; however these locales
    # are not supported yet. Add extra locales after Chrome supports them.
    ('nl', 'xkb:be::nld', 'Europe/Amsterdam', 'Dutch (Belgium)'),
    ('de', 'xkb:be::ger', 'Europe/Amsterdam', 'German (Belgium)'),
    ('fr', 'xkb:be::fra', 'Europe/Amsterdam', 'French (Belgium)'),

    # TODO(hungte) There is no valid keyboard layout for it-CH yet, so we use
    # the layout from it-IT. May update that in future.
    ('it-CH', 'xkb:it::ita',),

    # TODO(hungte) es419 has same issue as Belgium. Add extra locales after
    # Chrome supports them.
    ('es-419', 'xkb:latam::spa',),

    # Use 'en-GB' for Singapore and India because they are
    # British Commonwealth of Nations.
    # http://en.wikipedia.org/wiki/Commonwealth_of_Nations
    ('en-GB', 'xkb:us::eng', 'Asia/Kuala_Lumpur', 'English (Singapore)'),
    ('en-GB', 'xkb:us::eng', 'Asia/Calcutta', 'English (India)'),
)


def BuildRegionInformation(region_data):
  """Completes region information (see DEFAULT_LOCALE_KEYBOARD_MAP)."""
  data = list(region_data)
  while len(data) < 4:
    data.append(None)
  (locale, layout, timezone, description) = data

  # validate locale and description
  assert locale in CHROMEOS_LOCALE_DATABASE, "Invalid locale: %s" % repr(data)
  locale_data = CHROMEOS_LOCALE_DATABASE[locale]
  if (not description) or description.startswith('+'):
    description = '%s %s' % (locale_data[0],
                             description[1:] if description else '')
  # validate and derive timezone
  timezone = timezone or locale_data[1]
  if timezone not in CHROMEOS_TIMEZONE_LIST:
    while timezone in UNSUPPORTED_TIMEZONE_MAP:
      timezone = UNSUPPORTED_TIMEZONE_MAP[timezone]
    assert timezone in CHROMEOS_TIMEZONE_LIST, (
        "Unknown timezone: %s" % repr(data))
  return (locale, layout, timezone, description)
