#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# A stub script for init/startup

# This is used for the offline tests, where start up job may be required on
# the DUT. This file can be push to DUT to enable the process.
#
# init/startup will run scripts under init/main.d if $1 == 'main',
# let's mimic this behavior.
# The "$1" = "" case is for DUT test image using the old /etc/init version,
# which calls init/startup only once, without any argument.

INIT_BASE="$(dirname $(readlink -f $0))"

if [ "$1" = "main" -o "$1" = "" ]; then
  local test_script=""
  for test_script in ${INIT_BASE}/main.d/*; do
    if [ -x "${test_script}" ]; then
      "${test_script}"
    fi
  done
fi
