# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Data pulled from the Chromium source tree for testing. Yes, this is
# ugly! Ideally these would be pulled in directly from the Chromium
# source when building, but there is no reasonable way to do that.
# This is unfortunate, but manually copying-and-pasting data structures
# is still infinitely better than just eyeballing the data, which is
# how we used to check this.
#
# When adding new regions to regions.py or regions_overlay.py, you may
# need to re-copy-and-paste the contents of these data structures
# here.


# From <http://goo.gl/WSVUeE>.
CROS_TIME_ZONES = """
static const char* kTimeZones[] = {
    "Pacific/Midway",
    "Pacific/Honolulu",
    "America/Anchorage",
    "America/Los_Angeles",
    "America/Vancouver",
    "America/Tijuana",
    "America/Phoenix",
    "America/Denver",
    "America/Edmonton",
    "America/Chihuahua",
    "America/Regina",
    "America/Costa_Rica",
    "America/Chicago",
    "America/Mexico_City",
    "America/Winnipeg",
    "America/Bogota",
    "America/New_York",
    "America/Toronto",
    "America/Caracas",
    "America/Barbados",
    "America/Halifax",
    "America/Manaus",
    "America/Santiago",
    "America/St_Johns",
    "America/Sao_Paulo",
    "America/Araguaina",
    "America/Argentina/Buenos_Aires",
    "America/Argentina/San_Luis",
    "America/Montevideo",
    "America/Godthab",
    "Atlantic/South_Georgia",
    "Atlantic/Cape_Verde",
    "Atlantic/Azores",
    "Africa/Casablanca",
    "Europe/London",
    "Europe/Dublin",
    "Europe/Amsterdam",
    "Europe/Belgrade",
    "Europe/Berlin",
    "Europe/Brussels",
    "Europe/Madrid",
    "Europe/Paris",
    "Europe/Rome",
    "Europe/Stockholm",
    "Europe/Sarajevo",
    "Europe/Vienna",
    "Europe/Warsaw",
    "Europe/Zurich",
    "Africa/Windhoek",
    "Africa/Lagos",
    "Africa/Brazzaville",
    "Africa/Cairo",
    "Africa/Harare",
    "Africa/Maputo",
    "Africa/Johannesburg",
    "Europe/Helsinki",
    "Europe/Athens",
    "Asia/Amman",
    "Asia/Beirut",
    "Asia/Jerusalem",
    "Europe/Minsk",
    "Asia/Baghdad",
    "Asia/Riyadh",
    "Asia/Kuwait",
    "Africa/Nairobi",
    "Asia/Tehran",
    "Europe/Moscow",
    "Asia/Dubai",
    "Asia/Tbilisi",
    "Indian/Mauritius",
    "Asia/Baku",
    "Asia/Yerevan",
    "Asia/Kabul",
    "Asia/Karachi",
    "Asia/Ashgabat",
    "Asia/Oral",
    "Asia/Calcutta",
    "Asia/Colombo",
    "Asia/Katmandu",
    "Asia/Yekaterinburg",
    "Asia/Almaty",
    "Asia/Dhaka",
    "Asia/Rangoon",
    "Asia/Bangkok",
    "Asia/Jakarta",
    "Asia/Omsk",
    "Asia/Novosibirsk",
    "Asia/Shanghai",
    "Asia/Hong_Kong",
    "Asia/Kuala_Lumpur",
    "Asia/Singapore",
    "Asia/Manila",
    "Asia/Taipei",
    "Asia/Makassar",
    "Asia/Krasnoyarsk",
    "Australia/Perth",
    "Australia/Eucla",
    "Asia/Irkutsk",
    "Asia/Seoul",
    "Asia/Tokyo",
    "Asia/Jayapura",
    "Australia/Adelaide",
    "Australia/Darwin",
    "Australia/Brisbane",
    "Australia/Hobart",
    "Australia/Sydney",
    "Asia/Yakutsk",
    "Pacific/Guam",
    "Pacific/Port_Moresby",
    "Asia/Vladivostok",
    "Asia/Sakhalin",
    "Asia/Magadan",
    "Pacific/Auckland",
    "Pacific/Fiji",
    "Pacific/Majuro",
    "Pacific/Tongatapu",
    "Pacific/Apia",
    "Pacific/Kiritimati",
};
"""

# From <http://goo.gl/kVkht>.
CROS_ACCEPT_LANGUAGE_LIST = """
static const char* const kAcceptLanguageList[] = {
  "af",     // Afrikaans
  "am",     // Amharic
  "ar",     // Arabic
  "az",     // Azerbaijani
  "be",     // Belarusian
  "bg",     // Bulgarian
  "bh",     // Bihari
  "bn",     // Bengali
  "br",     // Breton
  "bs",     // Bosnian
  "ca",     // Catalan
  "co",     // Corsican
  "cs",     // Czech
  "cy",     // Welsh
  "da",     // Danish
  "de",     // German
  "de-AT",  // German (Austria)
  "de-CH",  // German (Switzerland)
  "de-DE",  // German (Germany)
  "el",     // Greek
  "en",     // English
  "en-AU",  // English (Australia)
  "en-CA",  // English (Canada)
  "en-GB",  // English (UK)
  "en-NZ",  // English (New Zealand)
  "en-US",  // English (US)
  "en-ZA",  // English (South Africa)
  "eo",     // Esperanto
  // TODO(jungshik) : Do we want to list all es-Foo for Latin-American
  // Spanish speaking countries?
  "es",     // Spanish
  "es-419", // Spanish (Latin America)
  "et",     // Estonian
  "eu",     // Basque
  "fa",     // Persian
  "fi",     // Finnish
  "fil",    // Filipino
  "fo",     // Faroese
  "fr",     // French
  "fr-CA",  // French (Canada)
  "fr-CH",  // French (Switzerland)
  "fr-FR",  // French (France)
  "fy",     // Frisian
  "ga",     // Irish
  "gd",     // Scots Gaelic
  "gl",     // Galician
  "gn",     // Guarani
  "gu",     // Gujarati
  "ha",     // Hausa
  "haw",    // Hawaiian
  "he",     // Hebrew
  "hi",     // Hindi
  "hr",     // Croatian
  "hu",     // Hungarian
  "hy",     // Armenian
  "ia",     // Interlingua
  "id",     // Indonesian
  "is",     // Icelandic
  "it",     // Italian
  "it-CH",  // Italian (Switzerland)
  "it-IT",  // Italian (Italy)
  "ja",     // Japanese
  "jw",     // Javanese
  "ka",     // Georgian
  "kk",     // Kazakh
  "km",     // Cambodian
  "kn",     // Kannada
  "ko",     // Korean
  "ku",     // Kurdish
  "ky",     // Kyrgyz
  "la",     // Latin
  "ln",     // Lingala
  "lo",     // Laothian
  "lt",     // Lithuanian
  "lv",     // Latvian
  "mk",     // Macedonian
  "ml",     // Malayalam
  "mn",     // Mongolian
  "mo",     // Moldavian
  "mr",     // Marathi
  "ms",     // Malay
  "mt",     // Maltese
  "nb",     // Norwegian (Bokmal)
  "ne",     // Nepali
  "nl",     // Dutch
  "nn",     // Norwegian (Nynorsk)
  "no",     // Norwegian
  "oc",     // Occitan
  "om",     // Oromo
  "or",     // Oriya
  "pa",     // Punjabi
  "pl",     // Polish
  "ps",     // Pashto
  "pt",     // Portuguese
  "pt-BR",  // Portuguese (Brazil)
  "pt-PT",  // Portuguese (Portugal)
  "qu",     // Quechua
  "rm",     // Romansh
  "ro",     // Romanian
  "ru",     // Russian
  "sd",     // Sindhi
  "sh",     // Serbo-Croatian
  "si",     // Sinhalese
  "sk",     // Slovak
  "sl",     // Slovenian
  "sn",     // Shona
  "so",     // Somali
  "sq",     // Albanian
  "sr",     // Serbian
  "st",     // Sesotho
  "su",     // Sundanese
  "sv",     // Swedish
  "sw",     // Swahili
  "ta",     // Tamil
  "te",     // Telugu
  "tg",     // Tajik
  "th",     // Thai
  "ti",     // Tigrinya
  "tk",     // Turkmen
  "to",     // Tonga
  "tr",     // Turkish
  "tt",     // Tatar
  "tw",     // Twi
  "ug",     // Uighur
  "uk",     // Ukrainian
  "ur",     // Urdu
  "uz",     // Uzbek
  "vi",     // Vietnamese
  "xh",     // Xhosa
  "yi",     // Yiddish
  "yo",     // Yoruba
  "zh",     // Chinese
  "zh-CN",  // Chinese (Simplified)
  "zh-TW",  // Chinese (Traditional)
  "zu",     // Zulu
};
"""

# From <http://goo.gl/xWNrUP>.
CROS_INPUT_METHODS = """
# U.S. English
xkb:us::eng     us      en-US,en-AU,id,fil,ms login
xkb:us:intl:eng us(intl)        en-US,nl,pt-BR login
xkb:us:altgr-intl:eng   us(altgr-intl)  en-US login
xkb:us:dvorak:eng       us(dvorak)      en-US login
xkb:us:colemak:eng      us(colemak)     en-US login
# U.S. English entiries have to be above the Dutch entry so that xkb:us:intl:eng
# will be selected as the default keyboard when the UI language is set to Dutch.

# Dutch
xkb:be::nld     be      nl login
# We don't support xkb:nl::nld. See b/4430951.

# French
xkb:fr::fra     fr      fr login
xkb:be::fra     be      fr login
xkb:ca::fra     ca      fr login
xkb:ch:fr:fra   ch(fr)  fr login
xkb:ca:multix:fra ca(multix) fr login

# German
xkb:de::ger     de      de login
xkb:de:neo:ger  de(neo) de login
xkb:be::ger     be      de login
xkb:ch::ger     ch      de login

# Japanese
# |kMozcJaInputMethodIds| in ibus_ui_controller.cc should also be updated when
# a new Mozc Japanese IME for another keyboard layout is added.
xkb:jp::jpn     jp      ja login

# Russian
xkb:ru::rus     ru      ru
xkb:ru:phonetic:rus     ru(phonetic)    ru

# Keyboard layouts.
xkb:br::por     br      pt-BR login
xkb:bg::bul     bg      bg
xkb:bg:phonetic:bul     bg(phonetic)    bg
xkb:ca:eng:eng  ca(eng) en-CA login
xkb:cz::cze     cz      cs login
xkb:cz:qwerty:cze       cz(qwerty)      cs login
xkb:ee::est     ee      et login
xkb:es::spa     es      es login
xkb:es:cat:cat  es(cat) ca login
xkb:dk::dan     dk      da login
xkb:gr::gre     gr      el
xkb:il::heb     il      he
xkb:latam::spa  latam   es,es-419 login
xkb:lt::lit     lt      lt login
xkb:lv:apostrophe:lav   lv(apostrophe)  lv login
xkb:hr::scr     hr      hr login
xkb:gb:extd:eng gb(extd)        en-GB login
xkb:gb:dvorak:eng       gb(dvorak)      en-GB login
xkb:fi::fin     fi      fi login
xkb:hu::hun     hu      hu login
xkb:it::ita     it      it login
xkb:is::ice     is      is login
xkb:no::nob     no      nb login
xkb:pl::pol     pl      pl login
xkb:pt::por     pt      pt-PT login
xkb:ro::rum     ro      ro login
xkb:se::swe     se      sv login
xkb:sk::slo     sk      sk
xkb:si::slv     si      sl login
xkb:rs::srp     rs      sr
xkb:tr::tur     tr      tr login
xkb:ua::ukr     ua      uk login
xkb:by::bel     by      be
xkb:am:phonetic:arm     am      hy
xkb:ge::geo     ge      ka
xkb:mn::mon     mn      mn
# TODO(yusukes): Support xkb:latam:deadtilde:spa and/or xkb:latam:nodeadkeys:spa
# if necessary.
"""
