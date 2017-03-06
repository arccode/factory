#!/bin/bash
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$0")"
. "${SCRIPT_DIR}/common.sh"
load_config

. "${SCRIPT_DIR}/status.sh"

# define Flags
DEFINE_boolean force "${FLAGS_FALSE}" \
    "force unmount, even if there are unstaged files"
DEFINE_boolean clean_temp "${FLAGS_TRUE}" \
    "remove the temp directory"

main() {
  FLAGS "$@" || exit $?
  eval set -- "${FLAGS_ARGV}"

  if ! is_simple_mode && [ "${FLAGS_force}" == "${FLAGS_FALSE}" ]; then
    eval "$(declare_status_list)"
    if [ "${result_length}" -gt 0 ]; then
      echo "There are some unstaged files:"

      print_status

      echo "aufs is not unmounted..."
      exit 1
    fi
  fi

  echo "unmounting aufs..."
  sudo umount "${WORKING_DIR}" || exit $?

  if is_simple_mode; then
    # in simple mode, OVERLAY_DIR is mounted as writable,
    # we need to cleanup OVERLAY_DIR
    callback() {
      local status="$1"
      local overlay="$2"
      local relative_path="$3"
      if [ "${status}" == "D" ] && \
         ( [ -e "${OVERLAY_DIR}/${relative_path}" ] || \
           [ -e "${FACTORY_DIR}/${relative_path}" ] ); then
        echo -n "${COLOR_RED}"
        echo "You tried to delete ${relative_path}, this will not be done..."
      fi
    }
    for_each_unstaged_file callback
    echo "${COLOR_NOR}"

    echo "Cleanup .wh.* files in ${OVERLAY_DIR}"
    sudo find "${OVERLAY_DIR}" -name '.wh.*' -delete
    sudo rm "${OVERLAY_DIR}/.aufs.config"
  else
    echo "clean up TEMP_DIR: ${TEMP_DIR}"
    rm -rf "${TEMP_DIR}"
  fi
}

# only execute main if this file is called directly
[ "$0" = "${BASH_SOURCE[0]}" ] && main "$@"
