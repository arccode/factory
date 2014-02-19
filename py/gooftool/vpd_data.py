#!/usr/bin/env python
# pylint: disable=C0301
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# This is a required test to check all VPD related information.


"""Collection of valid VPD values for ChromeOS."""

from cros.factory.l10n import regions


KEYBOARD_LAYOUT = set(','.join(x.keyboards)
                      for x in regions.REGIONS.itervalues())
INITIAL_LOCALE = set(','.join(x.language_codes)
                     for x in regions.REGIONS.itervalues())
INITIAL_TIMEZONE = set(x.time_zone for x in regions.REGIONS.itervalues())

KNOWN_VPD_FIELD_DATA = {
  'keyboard_layout': KEYBOARD_LAYOUT,
  'initial_locale': INITIAL_LOCALE,
  'initial_timezone': INITIAL_TIMEZONE,
  }
