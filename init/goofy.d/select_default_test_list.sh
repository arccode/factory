#!/bin/sh
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script tries to find if the active test list if already selected, and
# select the model-specific one if available.

# TODO(hungte) Fallback to 'generic_main' if 'main' is not defined. We can't do
# this now because we are still supporting both JSON and PY test lists at the
# same time, so not having JSON 'main' does not mean there's no PY 'main'.

TESTLISTS=/usr/local/factory/py/test/test_lists
ACTIVE_FILE="${TESTLISTS}/ACTIVE"
if [ -e "${ACTIVE_FILE}" ]; then
  exit
fi

MODEL="$(mosys platform model)"
if [ -e "${TESTLISTS}/main_${MODEL}.test_list.json" ]; then
  echo "main_${MODEL}" >"${ACTIVE_FILE}"
fi
