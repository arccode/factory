#!/bin/sh
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

main() {
  local job=""

  for job in "${SCRIPT_DIR}/inhibit_jobs/"*; do
    local job_name="$(basename "${job}")"
    local job_path="/etc/init/${job_name}.conf"
    if [ -e "${job_path}" ]; then
      mount --bind /dev/null "${job_path}"
    fi
  done
}

main
