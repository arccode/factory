#!/bin/sh
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This tool tries to find running Chrome session and redirect all opened pages
# to the given URL.

if [ "$#" != 1 ]; then
  echo "Usage: $0 URL" >&2
  exit 1
fi

TOOLS_DIR="$(dirname "$(readlink -f "$0")")/../py/tools"
exec "${TOOLS_DIR}/chrome_debugger.py" "Page.navigate" '{"url": "'"$*"'"}'
