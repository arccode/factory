#!/bin/sh
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Clear all factory test states when the internal storage has been changed.
# Note we can't call 'factory clear' because goofy (providing goofy_rpc) is not
# available at the moment.
echo "Device ID change detected, resetting all test results..."
TESTS_DATA="/var/factory/state/tests"
# We can't call the file tests.bak here, since shelve_utils assume that all
# files with prefix 'tests.' part of the shelve.
BACKUP_TESTS_DATA="${TESTS_DATA}_bak"
if [ -e "${TESTS_DATA}" ]; then
  rm -rf "${BACKUP_TESTS_DATA}"
  mv -f "${TESTS_DATA}" "${BACKUP_TESTS_DATA}"
fi
