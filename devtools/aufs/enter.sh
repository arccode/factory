#!/bin/bash
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$0")"
. "${SCRIPT_DIR}/common.sh"


DEFINE_boolean simple "${FLAGS_TRUE}" \
    "will mount OVERLAY_DIR as writable, TEMP_DIR will not be mounted" "s"


equery_outside_chroot() {
  local ebuild_name="$1"

  local equery_cmd="equery-${BOARD} which ${ebuild_name}"
  local sed_cmd='sed "s@${CROS_WORKON_SRCROOT}@${EXTERNAL_TRUNK_PATH}@"'

  # Since cros_sdk use an interactive shell to execute our command, there might
  # be other outputs (e.g. output while loading bashrc).  We only keep the last
  # line which ends with ebuild
  (set -o pipefail
   (cros_sdk sh -c "set -o pipefail; ${equery_cmd} | ${sed_cmd}") | \
       grep 'ebuild$' | tail -n 1)
}


main() {
  FLAGS "$@" || exit $?
  eval set -- "${FLAGS_ARGV}"

  if [ -z "${OVERLAY_DIR}" ]; then
    if [ -z "${BOARD}" ]; then
      echo "Please specify the board you'd like to work with"
      exit 1
    else
      echo "${BOARD}"
    fi

    if [ -n "${CROS_WORKON_SRCROOT}" ]; then
      # We are inside chroot
      EBUILD_PATH="$("equery-${BOARD}" which factory-board || \
                     "equery-${BOARD}" which chromeos-factory-board)"
    else
      EBUILD_PATH="$(equery_outside_chroot factory-board || \
                     equery_outside_chroot chromeos-factory-board)"
    fi
    OVERLAY_DIR="$(realpath "$(dirname "${EBUILD_PATH}")/files")"
  fi


  if [ "${FLAGS_simple}" == "${FLAGS_TRUE}" ]; then
    TEMP_DIR=/dev/null
    AUFS_BRANCH="br=${OVERLAY_DIR}=rw:${FACTORY_DIR}=ro"
  else
    TEMP_DIR="$(mktemp -d "/tmp/factory_dev_XXXXXX")"
    AUFS_BRANCH="br=${TEMP_DIR}=rw:${OVERLAY_DIR}=ro:${FACTORY_DIR}=ro"
  fi

  echo "the working directory will be ${WORKING_DIR}"
  mkdir -p "${WORKING_DIR}"

  sudo mount -t aufs \
    -o "${AUFS_BRANCH}" \
    -o udba=reval none "${WORKING_DIR}" || exit $?
  save_config
}

main "$@"
