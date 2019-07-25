#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# goofy_control.sh will check disk usage and abort when running out of
# disk space. Some files in stateful partition aren't needed for factory
# test but they consume several hundreds of MB. This script removes those
# unused files to get more disk space for goofy_control to start.

ROOT="/mnt/stateful_partition"
UNUSED_STATEFUL_DIRS="
  ${ROOT}/dev_image/telemetry
  ${ROOT}/dev_image/lib/debug/
  ${ROOT}/dev_image/*-cros-linux-gnu
"

main() {
  for dir in ${UNUSED_STATEFUL_DIRS}; do
    if [ -d "${dir}" ]; then
      echo "Removing unused dir ${dir} ..."
      rm -rf "${dir}"
    fi
  done
}

main "$@"
