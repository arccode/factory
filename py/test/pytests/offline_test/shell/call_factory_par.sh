#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

task_{%id%} () {
  local tmp_stderr="$(mktemp)"
  local tmp_stdout="$(mktemp)"

  {%cmd%} 2>"${tmp_stderr}" >"${tmp_stdout}"

  local return_value="$?"

  info "$(cat "${tmp_stdout}")"
  error "$(cat "${tmp_stderr}")"

  rm -f "${tmp_stdout}" "${tmp_stderr}"

  return "${return_value}"
}
