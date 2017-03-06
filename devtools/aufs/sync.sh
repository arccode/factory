#!/bin/bash
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$0")"
. "${SCRIPT_DIR}/common.sh"
load_config

. "${SCRIPT_DIR}/status.sh"


DEFINE_boolean interactive "${FLAGS_FALSE}" \
    "for each file, ask which branch should be affected" "i"


sync_one_file() {
  local status="$1"
  local overlay="$2"
  local relative_path="$3"

  overlay="$(convert_overlay_flag_to_path "${overlay}")"

  case "${status}" in
    D)
      for overlay in "${OVERLAY_DIR}" "${FACTORY_DIR}"; do
        if [ -e "${overlay}/${relative_path}" ]; then
          echo "deleting ${relative_path} from ${overlay}"
          rm "${overlay}/${relative_path}"
        fi
      done
      local basename="$(basename "${relative_path}")"
      rm -f "${RW_DIR}/$(dirname "${relative_path}")/.wh.${basename}"
      ;;
    M)
      if [ "${FLAGS_interactive}" == "${FLAGS_TRUE}" ]; then
        read -n1 -p \
          "Modify ${relative_path} in [F]actory/[O]verlay/[A]uto/[C]ancel " \
          answer
        echo
      else
        answer=a
      fi

      case "${answer}" in
        F|f)
          overlay="${FACTORY_DIR}"
          ;;
        O|o)
          overlay="${OVERLAY_DIR}"
          ;;
        A|a)
          ;; # does nothing, OVERLAY_DIR should already be set
        *)
          overlay=  # unset overlay to cancel
      esac

      if [ -n "${overlay}" ]; then
        echo "sync ${relative_path} to ${overlay}"
        mv "${RW_DIR}/${relative_path}" "${overlay}/${relative_path}"
      fi
      ;;
    A)
      if [ "${FLAGS_interactive}" == "${FLAGS_TRUE}" ]; then
        read -n1 -p \
          "Move new file ${relative_path} to [F]actory/[O]verlay/[C]ancel " \
          answer
        echo
      else
        answer="O"
      fi
      case "${answer}" in
        F|f)
          echo "add ${relative_path} to ${FACTORY_DIR}"
          mv "${RW_DIR}/${relative_path}" "${FACTORY_DIR}/${relative_path}"
          ;;
        O|o)
          echo "add ${relative_path} to ${OVERLAY_DIR}"
          mv "${RW_DIR}/${relative_path}" "${OVERLAY_DIR}/${relative_path}"
          ;;
      esac
      ;;
    *)
      echo "cannot sync file ${relative_path}"
      ;;
  esac
}


find_file_path_and_sync() {
  # $1 is given by user input, might be path relative to users working directory
  local relative_path="$(get_relative_path "$1")"

  if [ -z "${relative_path}" ]; then
    return
  fi

  local overlay="$(detect_overlay "${relative_path}")"
  local status="$(detect_status "${relative_path}" "${overlay}")"

  sync_one_file "${status}" "${overlay}" "${relative_path}"
}


merge_file() {
  if [ $# -eq 0 ]; then
    for_each_unstaged_file sync_one_file
  else
    for file in "$@"; do
      find_file_path_and_sync "${file}"
    done
  fi
}


main() {
  FLAGS "$@" || exit $?
  eval set -- "${FLAGS_ARGV}"

  if is_simple_mode; then
    cat << EOF
You are in simple mode, you should not sync anything from board overlay to
factory repo, do you want to continue? [y/N]
EOF
    read -s -n1 answer
    if [ "${answer}" != "Y" ] && [ "${answer}" != "y" ]; then
      echo "cancelled.."
      exit 0
    fi
  fi
  merge_file "$@"
}


# only execute main if this file is called directly
[ "$0" = "${BASH_SOURCE[0]}" ] && main "$@"
