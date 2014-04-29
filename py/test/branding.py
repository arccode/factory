#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Constants for branding parameters (rlz_brand_id, customization_id)."""


import re


RLZ_BRAND_CODE_REGEXP = re.compile('^[A-Z]{4}$')
CUSTOMIZATION_ID_REGEXP = re.compile('^[A-Z0-9]+(-[A-Z0-9]+)?$')

BRAND_CODE_PATH = '/opt/oem/etc/BRAND_CODE'
