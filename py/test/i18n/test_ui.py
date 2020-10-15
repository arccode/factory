# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for methods of creating i18n UIs."""

from cros.factory.test.i18n import translation


def MakeI18nLabel(label):
  """Make an i18n label.

  Args:
    label: The string of the label, or the translation dict obtained by
        ``i18n._``.

  Returns:
    The HTML of label, that can be used in Goofy.

  Example:
    MakeI18nLabel(
        i18n._(
            'This is a label with name "{name}" and value {value}',
            name=i18n._('example label name'),
            value='value'))
  """
  label = translation.Translated(label)

  html = []
  for locale in translation.LOCALES:
    translated_label = label[locale]
    html_class = 'goofy-label-' + locale
    html.append(u'<span class="%s">%s</span>' % (html_class, translated_label))
  return ''.join(html)


def GetStyleSheet():
  """Return a stylesheet that can be used to style i18n labels properly."""
  styles = []
  for locale in translation.LOCALES:
    styles.append("""
    .goofy-label-{locale} {{
      display: none;
    }}
    .goofy-locale-{locale} .goofy-label-{locale} {{
      display: inline;
    }}""".format(locale=locale))
  return '\n'.join(styles)
