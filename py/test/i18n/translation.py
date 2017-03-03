# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to handle internationalization in goofy tests."""

from __future__ import print_function
import gettext
import glob
import logging
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths


DOMAIN = 'factory'
DEFAULT_LOCALE = 'en-US'

LOCALE_DIR = os.path.join(paths.FACTORY_PATH, 'locale')
# All supported locales by Goofy
LOCALES = [DEFAULT_LOCALE] + [os.path.basename(p)
                              for p in glob.glob(os.path.join(LOCALE_DIR, '*'))]

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
  return _GetTranslations(locale).ugettext(text) if text else ''


def _(text):
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


def Translated(obj, translate=True, backward_compatible=True):
  """Ensure that the argument is a translation dict, pass it to _ or
  NoTranslation if it isn't.

  This will also make sure that the return translation dict contains all
  supported locales. The value of DEFAULT_LOCALE would be used to fill in
  locales not in the input obj regardless of the argument translate.

  Args:
    obj: The string to be translated, or the translation dict.
    translate: True to pass things that are not translation dict to _, False
        to pass to NoTranslation.
    backward_compatible: if True, also accept the case that obj is a tuple
        of form ``(en, zh)``.

  Returns:
    The translation dict.
  """
  # TODO(pihsun): backward_compatible mode should be removed when all tests /
  #   test_lists are migrated to the new format.
  if isinstance(obj, tuple) and len(obj) == 2 and backward_compatible:
    logging.warn('Use of tuple form %r is deprecated. '
                 "Please use {'en-US': %r, 'zh-CN': %r} instead.",
                 obj, obj[0], obj[1])
    obj = {'en-US': obj[0], 'zh-CN': obj[1]}

  if isinstance(obj, dict):
    if DEFAULT_LOCALE not in obj:
      raise ValueError("%r doesn't contains default locale %s." % (
          obj, DEFAULT_LOCALE))
    default = obj.get(DEFAULT_LOCALE)
    obj = {locale: obj.get(locale, default) for locale in LOCALES}
  else:
    obj = (_(obj) if translate else NoTranslation(obj))
  return obj
