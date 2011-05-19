#!/usr/bin/env python
#
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# This is a required test to check all VPD related information.

""" gft_vpd.py: Check if the VPD data is valid for ChromeOS. """


import bmpblk
import gft_common
import gft_report
import os
import sys

from gft_common import ErrorMsg, WarningMsg, VerboseMsg, DebugMsg, ErrorDie

# VPD Keys
KEY_KEYBOARD_LAYOUT = 'keyboard_layout'
KEY_INITIAL_LOCALE = 'initial_locale'
KEY_INITIAL_TIMEZONE = 'initial_timezone'

# keyboard_layout: http://git.chromium.org/gitweb/?p=chromiumos/platform/assets.git;a=blob;f=input_methods/whitelist.txt;hb=HEAD
CHROMEOS_KEYBOARD_LAYOUT = [
  'xkb:nl::nld',
  'xkb:be::nld',
  'xkb:fr::fra',
  'xkb:be::fra',
  'xkb:ca::fra',
  'xkb:ch:fr:fra',
  'xkb:de::ger',
  'xkb:de:neo:ger',
  'xkb:be::ger',
  'xkb:ch::ger',
  'xkb:jp::jpn',
  'xkb:ru::rus',
  'xkb:ru:phonetic:rus',
  'xkb:us::eng',
  'xkb:us:intl:eng',
  'xkb:us:altgr-intl:eng',
  'xkb:us:dvorak:eng',
  'xkb:us:colemak:eng',
  'xkb:br::por',
  'xkb:bg::bul',
  'xkb:bg:phonetic:bul',
  'xkb:ca:eng:eng',
  'xkb:cz::cze',
  'xkb:ee::est',
  'xkb:es::spa',
  'xkb:es:cat:cat',
  'xkb:dk::dan',
  'xkb:gr::gre',
  'xkb:il::heb',
  'xkb:kr:kr104:kor',
  'xkb:latam::spa',
  'xkb:lt::lit',
  'xkb:lv:apostrophe:lav',
  'xkb:hr::scr',
  'xkb:gb:extd:eng',
  'xkb:gb:dvorak:eng',
  'xkb:fi::fin',
  'xkb:hu::hun',
  'xkb:it::ita',
  'xkb:no::nob',
  'xkb:pl::pol',
  'xkb:pt::por',
  'xkb:ro::rum',
  'xkb:se::swe',
  'xkb:sk::slo',
  'xkb:si::slv',
  'xkb:rs::srp',
  'xkb:tr::tur',
  'xkb:ua::ukr',
]

# initial_locale: http://google.com/codesearch/p?#OAMlx_jo-ck/src/ui/base/l10n/l10n_util.cc&q=kAcceptLanguageList
CHROMEOS_INITIAL_LOCALE = [
  "af",
  "am",
  "ar",
  "az",
  "be",
  "bg",
  "bh",
  "bn",
  "br",
  "bs",
  "ca",
  "co",
  "cs",
  "cy",
  "da",
  "de",
  "de-AT",
  "de-CH",
  "de-DE",
  "el",
  "en",
  "en-AU",
  "en-CA",
  "en-GB",
  "en-NZ",
  "en-US",
  "en-ZA",
  "eo",
  "es",
  "es-419",
  "et",
  "eu",
  "fa",
  "fi",
  "fil",
  "fo",
  "fr",
  "fr-CA",
  "fr-CH",
  "fr-FR",
  "fy",
  "ga",
  "gd",
  "gl",
  "gn",
  "gu",
  "ha",
  "haw",
  "he",
  "hi",
  "hr",
  "hu",
  "hy",
  "ia",
  "id",
  "is",
  "it",
  "it-CH",
  "it-IT",
  "ja",
  "jw",
  "ka",
  "kk",
  "km",
  "kn",
  "ko",
  "ku",
  "ky",
  "la",
  "ln",
  "lo",
  "lt",
  "lv",
  "mk",
  "ml",
  "mn",
  "mo",
  "mr",
  "ms",
  "mt",
  "nb",
  "ne",
  "nl",
  "nn",
  "no",
  "oc",
  "om",
  "or",
  "pa",
  "pl",
  "ps",
  "pt",
  "pt-BR",
  "pt-PT",
  "qu",
  "rm",
  "ro",
  "ru",
  "sd",
  "sh",
  "si",
  "sk",
  "sl",
  "sn",
  "so",
  "sq",
  "sr",
  "st",
  "su",
  "sv",
  "sw",
  "ta",
  "te",
  "tg",
  "th",
  "ti",
  "tk",
  "to",
  "tr",
  "tt",
  "tw",
  "ug",
  "uk",
  "ur",
  "uz",
  "vi",
  "xh",
  "yi",
  "yo",
  "zh",
  "zh-CN",
  "zh-TW",
  "zu",
]

# initial_timezone: http://google.com/codesearch/p?#OAMlx_jo-ck/src/chrome/browser/ui/webui/options/chromeos/system_settings_provider.cc&q=kTimeZones
CHROMEOS_INITIAL_TIMEZONE = [
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


def ParseRoVpdData(vpd_source=None, verbose=False):
  vpd_cmd = '-f %s' % vpd_source if vpd_source else ''
  ro_vpd = gft_report.ParseVPDOutput(
      gft_common.SystemOutput("vpd -i RO_VPD -l %s" % vpd_cmd,
                              progress_message="Reading RO VPD",
                              show_progress=verbose).strip())
  return ro_vpd


def ValidateVpdData(vpd_source=None, verbose=False):
  mandatory_fields = {
      KEY_KEYBOARD_LAYOUT: CHROMEOS_KEYBOARD_LAYOUT,
      KEY_INITIAL_LOCALE: CHROMEOS_INITIAL_LOCALE,
      KEY_INITIAL_TIMEZONE: CHROMEOS_INITIAL_TIMEZONE,
  }
  ro_vpd = ParseRoVpdData(vpd_source, verbose)
  for field, valid_list in mandatory_fields.items():
    if field not in ro_vpd:
      ErrorDie('Missing required VPD value: %s' % field)
    if ro_vpd[field] not in valid_list:
      ErrorDie('Invalid value in VPD [%s]: %s' % (field, ro_vpd[field]))
  return True


#############################################################################
# Console main entry
@gft_common.GFTConsole
def main():
  """ Main entry as a utility. """
  vpd_source = None
  verbose = True
  if len(sys.argv) > 2:
    ErrorDie('Usage: %s [vpd_source]' % sys.argv[0])
  elif len(sys.argv) == 2:
    vpd_source = sys.argv[1]
    verbose = False
  ValidateVpdData(vpd_source, verbose)
  print "VPD verified OK."

if __name__ == "__main__":
  main()
