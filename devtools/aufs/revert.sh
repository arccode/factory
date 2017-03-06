#!/bin/bash
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$0")"
. "${SCRIPT_DIR}/common.sh"
load_config

. "${SCRIPT_DIR}/status.sh"

revert_one_file() {
  local status="$1"
  local overlay="$2"
  local relative_path="$3"

  case "${status}" in
    D)
      local basename="$(basename "${relative_path}")"
      rm -f "${RW_DIR}/$(dirname "${relative_path}")/.wh.${basename}"
      ;;
    M|A)
      rm "${RW_DIR}/${relative_path}"
      ;;
    *)
      echo "You cannot revert ${relative_path}, perhaps git can help you?"
      ;;
  esac
}

find_file_path_and_revert() {
  # $1 is given by user input, might be path relative to users working directory
  local relative_path="$(get_relative_path "$1")"

  if [ -z "${relative_path}" ]; then
    return
  fi

  local overlay="$(detect_overlay "${relative_path}")"
  local status="$(detect_status "${relative_path}" "${overlay}")"

  revert_one_file "${status}" "${overlay}" "${relative_path}"
}

main() {
  FLAGS "$@" || exit $?
  eval set -- "${FLAGS_ARGV}"

  if [ $# -eq 0 ]; then
    for_each_unstaged_file revert_one_file
  else
    for file in "$@"; do
      find_file_path_and_revert "${file}"
    done
  fi
  drop_cache
}

# only execute main if this file is called directly
[ "$0" = "${BASH_SOURCE[0]}" ] && main "$@"
