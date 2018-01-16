# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import translation
from cros.factory.test.i18n import string_utils

Translation = translation.Translation
NoTranslation = translation.NoTranslation
Translated = translation.Translated
_ = string_utils._
StringFormat = string_utils.StringFormat
HTMLEscape = string_utils.HTMLEscape
