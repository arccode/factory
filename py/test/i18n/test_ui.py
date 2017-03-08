# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for methods of creating i18n UIs."""

from __future__ import print_function

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import string_utils
from cros.factory.test.i18n import translation


def MakeI18nLabel(_label, **kwargs):
  """Make an i18n label.

  Args:
    _label: The string of the label, or the translation dict obtained by
        ``i18n._``. We use _label instead of label to avoid conflict with
        argument in kwargs.
    kwargs: Each extra argument should have value either a string or a
        translation dict obtained by ``i18n._``. This would be passed as
        arguments for python str.format() on translated string.

  Returns:
    The HTML of label, that can be used in Goofy.

  Example:
    MakeI18nLabel(
        i18n._('This is a label with name "{name}" and value {value}'),
        name=i18n._('example label name'),
        value=i18n.NoTranslation('value'))
  """
  return MakeI18nLabelWithClass(_label, '', **kwargs)


def MakeI18nLabelWithClass(_label, _class, **kwargs):
  """Make an i18n label with extra HTML class.

  Args:
    _label: The string of the label, or the translation dict obtained by
        ``i18n._``. We use _label instead of label to avoid conflict with
        argument in kwargs.
    _class: A string of extra HTML classes that should be set on the span.
    kwargs: Each extra argument should have value either a string or a
        translation dict obtained by ``i18n._``. This would be passed as
        arguments for python str.format() on translated string.

  Returns:
    The HTML of label, that can be used in Goofy.

  Example:
    MakeI18nLabelWithClass(
        i18n._('This is a label with name "{name}" and value {value}'),
        'large test-error',
        name=i18n._('example label name'),
        value=i18n.NoTranslation('value'))
  """

  label = translation.Translated(_label)
  label = string_utils.StringFormat(label, **kwargs)

  html = []
  for locale in translation.LOCALES:
    translated_label = label[locale]
    html_class = 'goofy-label-' + locale
    if _class:
      html_class += ' ' + _class
    html.append(u'<span class="%s">%s</span>' % (html_class, translated_label))
  return ''.join(html)
