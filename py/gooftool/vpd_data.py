#!/usr/bin/env python
# pylint: disable=C0301
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# This is a required test to check all VPD related information.


"""Collection of valid VPD values for ChromeOS."""

import factory_common  # pylint: disable=W0611
from cros.factory.l10n import regions


REGION_CODES = set(regions.REGIONS.iterkeys())

KNOWN_VPD_FIELD_DATA = {
    'region': REGION_CODES,
}
