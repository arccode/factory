#!/bin/bash
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$0")"
. "${SCRIPT_DIR}/common.sh"
load_config

. "${SCRIPT_DIR}/status.sh"

# Call git-diff with given files
# Arguments:
#   1. new_file: path to the new file
#   2. old_file: path to the old file
diff_one_file() {
  local new_file="$1"
  local old_file="$2"

  if [ ! -e "${new_file}" ]; then
    new_file="/dev/null"
  fi
  if [ ! -e "${old_file}" ]; then
    old_file="/dev/null"
  fi
  git diff --no-index --color "${old_file}" "${new_file}"
}

# Given a file name, find the corresponding file in RO branch, and show their
# changes.
# Arguments:
#   1. file path: a file path given by user, might be relative path
find_file_path_and_diff() {
  # $1 is given by user input, might be path relative to users working directory
  local relative_path="$(get_relative_path "$1")"

  if [ -z "${relative_path}" ]; then
    return
  fi

  local overlay="$(detect_overlay "${relative_path}")"
  overlay="$(convert_overlay_flag_to_path "${overlay}")"

  diff_one_file "${RW_DIR}/${relative_path}" "${overlay}/${relative_path}"
}

main() {
  FLAGS "$@" || exit $?
  eval set -- "${FLAGS_ARGV}"

  (
    if [ $# -eq 0 ]; then
      callback() {
        local overlay="$2"
        local relative_path="$3"

        overlay="$(convert_overlay_flag_to_path "${overlay}")"
        diff_one_file "${RW_DIR}/${relative_path}" \
                      "${overlay}/${relative_path}"
      }

      for_each_unstaged_file callback
    else
      for file in "$@"; do
        find_file_path_and_diff "${file}"
      done
    fi
  ) | less -FRSX
}


# only execute main if this file is called directly
[ "$0" = "${BASH_SOURCE[0]}" ] && main "$@"
