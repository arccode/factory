#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

task_{%id%} () {
  local shared_memory_path="{%shared_memory_path%}"
  if [ -n "${shared_memory_path}" ]; then
    toybox mount -o remount,size=100% "${shared_memory_path}"
  fi
  local output="$(mktemp)"

  factory_stressapptest -m {%cpu_count%} -M {%mem_usage%} \
      -s {%seconds%} {%disk_thread%} | tee "${output}"
  local return_value="$?"

  [ "${return_value}" = 0 ] && grep -q "Status: PASS" "${output}"
  return_value="$?"

  rm -rf "${output}"

  return "${return_value}"
}
