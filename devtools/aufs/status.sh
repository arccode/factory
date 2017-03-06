#!/bin/bash
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$0")"
. "${SCRIPT_DIR}/common.sh"
load_config

if is_simple_mode; then
  RW_DIR="${OVERLAY_DIR}"
else
  RW_DIR="${TEMP_DIR}"
fi

convert_overlay_flag_to_path() {
  case "$1" in
    O)
      echo "${OVERLAY_DIR}"
      ;;
    F)
      echo "${FACTORY_DIR}"
      ;;
  esac
}

detect_overlay() {
  # detect which overlay the file belongs to,
  #   "O" for board overlay
  #   "F" for factory repo
  #   " " for none
  # if the file could be found in both board overlay and factory repo, "O" will
  # be returned.

  local file="$1"
  local relative_path="${file#${RW_DIR}/}"

  if is_simple_mode; then
    if [ -e "${FACTORY_DIR}/${relative_path}" ]; then
      echo "F"
    else
      echo " "
    fi
  else
    # since the file in board overlay can override the file in factory repo, we
    # have to detect board overlay first.
    if [ -e "${OVERLAY_DIR}/${relative_path}" ]; then
      echo "O"
    elif [ -e "${FACTORY_DIR}/${relative_path}" ]; then
      echo "F"
    else
      echo " "
    fi
  fi
}

detect_status() {
  # detect file status
  #   "M" for modified
  #   "D" for deleted
  #   "A" for new file
  local file="$1"
  local overlay="$2"
  local relative_path="${file#${RW_DIR}/}"
  local basename="$(basename "${relative_path}")"
  local dirname="$(dirname "${relative_path}")"

  if [[ "${basename}" == ".wh."* ]]; then
    echo "D"
  elif [[ "${overlay}" == " " ]]; then
    if ! is_simple_mode; then
      echo "A"
    fi
  else
    if [ -e "${RW_DIR}/${dirname}/.wh.${basename}" ]; then
      # found whiteout file
      echo "D"
    else
      echo "M"
    fi
  fi
}

get_file_path_of_deleted_file() {
  local whiteout_path="$1"
  local relative_path="${whiteout_path#${RW_DIR}/}"
  local basename="$(basename "${relative_path}")"
  local dirname="$(dirname "${relative_path}")"

  if [[ "${basename}" != ".wh."* ]]; then
    echo "${whiteout_path} is not a whiteout marker" >2
  else
    local filename="${basename#.wh.}"
    echo "${dirname}/${filename}"
  fi
}

get_relative_path() {
  local file="$(realpath "$1")"
  if [[ "${file}" == "${WORKING_DIR}/"* ]]; then
    echo "${file#${WORKING_DIR}/}"
  elif [[ "${file}" == "${RW_DIR}/"* ]]; then
    echo "${file#${RW_DIR}/}"
  else
    echo "${file} is not a file under ${WORKING_DIR} or ${RW_DIR}" >2
  fi
}

# Returns true if we don't need to care about this file
should_ignore_this_file() {
  local file="$1"
  [[ "${file}" =~ "${RW_DIR}/.wh..".* || \
     "${file}" == "${RW_DIR}/.aufs.config" ]]
}

# This function will declare "result_length" and "result" variable,
# which is a list of changed files.
# See for_each_unstaged_file for example.
declare_status_list() {
  declare -A result
  local result_length=0
  while IFS= read -r -d '' file ; do
    if should_ignore_this_file "${file}"; then
      continue
    fi

    local overlay="$(detect_overlay "${file}")"
    local status="$(detect_status "${file}" "${overlay}")"

    if [ -z "${status}" ]; then
      # this file is neither added, deleted nor modified, skip this file
      continue
    elif [[ "${status}" == "D" ]]; then
      local relative_path="$(get_file_path_of_deleted_file "${file}")"
      local overlay="$(detect_overlay "${relative_path}")"
    else
      local relative_path="${file#${RW_DIR}/}"
    fi
    result["${result_length},status"]="${status}"
    result["${result_length},overlay"]="${overlay}"
    result["${result_length},relative_path"]="${relative_path}"
    result_length="$((result_length + 1))"
  done < <(find "${RW_DIR}" '(' -type f -o -type l ')' -a -print0 2>/dev/null)
  if [ "${result_length}" -gt 0 ]; then
    declare -p result
  fi
  declare -p result_length
}

# Calls callback function for each unstaged file, the callback function should
# take 3 arugments, here is an example:
#   callback() {
#     local status="$1"
#     local overlay="$2"
#     local relative_path="$3"
#     ...
#   }
for_each_unstaged_file() {
  local callback="$1"

  eval "$(declare_status_list)"

  if [ "${result_length}" -eq 0 ]; then
    echo "No unstaged file"
    return
  fi

  for ((i = 0; i < result_length; ++i)) do
    local status="${result[$i,status]}"
    local overlay="${result[$i,overlay]}"
    local relative_path="${result[$i,relative_path]}"

    "${callback}" "${status}" "${overlay}" "${relative_path}"
  done
}

print_status() {
  callback() {
    local status="$1"
    local overlay="$2"
    local relative_path="$3"

    if [ "${status}" == "D" ]; then
      status="${COLOR_RED}${status}${COLOR_NOR}"
    else
      status="${COLOR_GRN}${status}${COLOR_NOR}"
    fi
    echo "${status}${overlay} ${relative_path}"
  }

  echo
  echo "Modified files:"

  for_each_unstaged_file callback
}

main() {
  FLAGS "$@" || exit $?
  eval set -- "${FLAGS_ARGV}"

  print_status
}

# only execute main if this file is called directly
[ "$0" = "${BASH_SOURCE[0]}" ] && main "$@"
