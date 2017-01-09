#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

task_{%id%} () {
  local output="$(mktemp)"

  if {%is_file%}; then
    if [ ! -e {%device_path%} ]; then
      # file not exists, create one
      touch {%device_path%}
      truncate -s "$(({%sector_size%} * {%last_block%}))"
    fi
  fi

  badblocks -fw -b {%sector_size%} -e {%max_errors%} -o "${output}" \
      {%device_path%} {%last_block%} {%first_block%}
  local badblocks_return_value="$?"

  sync

  if {%is_file%}; then
    rm -f {%device_path%}
  fi

  # Compute return value.
  [ "${badblocks_return_value}" = 0 -a "$(stat -c '%s' "${output}")" = 0 ]
  local return_value="$?"

  # Remove temp file.
  rm -f "${output}"

  return "${return_value}"
}
