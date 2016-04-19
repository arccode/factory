#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

task_{%id%} () {
  local shared_memory_path="{%shared_memory_path%}"
  if [ -n "${shared_memory_path}" ]; then
    toybox mount -o remount,size=100% "${shared_memory_path}"
  fi
  local tmpdir="$(mktemp -d)"
  local output="$(stressapptest -m {%cpu_count%} -M {%mem_usage%} \
                  -s {%seconds%} {%disk_thread%})"
  local return_value="$?"
  rm -rf "${tmpdir}"

  if ! echo "${output}" | grep -q "Status: PASS" ; then
    die "${output}"
  fi

  return "${return_value}"
}
