# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to handle internationalization in goofy tests."""

import gettext
import glob
import json
import os

from cros.factory.test.env import paths
from cros.factory.utils import string_utils


DOMAIN = 'factory'

DEFAULT_LOCALE = 'en-US'
"""The default locale used in code."""

LOCALE_DIR = os.path.join(paths.FACTORY_DIR, 'locale')
# All supported locales by Goofy.
LOCALES = [DEFAULT_LOCALE] + sorted(
    [os.path.basename(p) for p in glob.glob(os.path.join(LOCALE_DIR, '*'))])

# gettext.Translations objects for all supported locales.
# Note: For locale = en-US, we don't actually have a translation file for
# english-to-english, so fallback is always used.
# We delay the construct of _TRANSLATIONS_DICT until the first call of
# GetTranslation, so it's easier for unittest to mock things.
_TRANSLATIONS_DICT = {}

def _GetTranslations(locale):
  if locale not in LOCALES:
    raise ValueError('Unsupported locale: %s' % locale)
  if locale not in _TRANSLATIONS_DICT:
    _TRANSLATIONS_DICT[locale] = gettext.translation(
        DOMAIN, LOCALE_DIR, [locale], fallback=True)
  return _TRANSLATIONS_DICT[locale]


def GetTranslation(text, locale):
  """Get translated string in a locale.

  Args:
    text: The string to be translated.
    locale: target locale.

  Returns:
    Translated string, or ``text`` if there's no translation.
  """
  # Do not translate empty string since it's the key of metadata in translation
  # object.
  return _GetTranslations(locale).gettext(text) if text else ''


def Translation(text):
  """Get the translation dict in all supported locales of a string.

  Args:
    text: The string to be translated.

  Returns:
    The translation dict for all supported locales.
  """
  return {locale: GetTranslation(text, locale) for locale in LOCALES}


def NoTranslation(obj):
  """Get a translation dict that maps the input unmodified for all supported
  locales.

  Used to explicitly set an object as don't translate when passing to various
  i18n functions.

  Args:
    obj: The object to be used.

  Returns:
    The translation dict for all supported locales.
  """
  return {locale: obj for locale in LOCALES}


def Translated(obj, translate=True):
  """Ensure that the argument is a translation dict, pass it to
  :func:`Translation` or :func:`NoTranslation` if it isn't.

  This will also make sure that the return translation dict contains all
  supported locales. The value of :const:`DEFAULT_LOCALE` would be used to fill
  in locales not in the input obj regardless of the argument translate.

  Args:
    obj: The string to be translated, or the translation dict.
    translate: True to pass things that are not translation dict to
        :func:`Translation`, False to pass to :func:`NoTranslation`.

  Returns:
    The translation dict.
  """
  if isinstance(obj, dict):
    if DEFAULT_LOCALE not in obj:
      raise ValueError(
          "%r doesn't contain the default locale %s." % (obj, DEFAULT_LOCALE))
    default = obj[DEFAULT_LOCALE]
    obj = {
        locale: string_utils.DecodeUTF8(obj.get(locale, default))
        for locale in LOCALES
    }
  else:
    obj = (Translation(obj) if translate else NoTranslation(obj))
  return obj


def GetAllTranslations():
  """Get translations for all available text."""
  all_keys = set()
  for locale in LOCALES:
    translations = _GetTranslations(locale)
    if not isinstance(translations, gettext.GNUTranslations):
      continue
    # pylint: disable=protected-access
    all_keys.update(translations._catalog)

  all_translations = []
  for key in all_keys:
    if key:
      all_translations.append(Translation(key))
  return all_translations


def GetAllI18nDataJS():
  """Return a javascript that contains all i18n-related things."""
  return json.dumps({'translations': GetAllTranslations(), 'locales': LOCALES})
