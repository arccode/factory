#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Migrates legacy "DUT API" implementation to new "Device API" location.

FACTORY_BASE="/usr/local/factory"

LEGACY_BOARDS="${FACTORY_BASE}/py/test/dut/boards"
DEVICE_BOARDS="${FACTORY_BASE}/py/device/boards"

if [ -d "${LEGACY_BOARDS}" ]; then
  mv "${LEGACY_BOARDS}"/* ${DEVICE_BOARDS}/.
  rmdir "${LEGACY_BOARDS}"
  rmdir "$(dirname "${LEGACY_BOARDS}")"
  echo "
    Migrated legacy DUT API board implementations from ${LEGACY_BOARDS} to
    ${DEVICE_BOARDS}.
    "
fi
