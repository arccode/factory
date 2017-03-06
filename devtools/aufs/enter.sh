#!/bin/bash
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$0")"
. "${SCRIPT_DIR}/common.sh"


DEFINE_boolean simple "${FLAGS_TRUE}" \
    "will mount OVERLAY_DIR as writable, TEMP_DIR will not be mounted" "s"


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
    EBUILD_PATH="$("equery-${BOARD}" which factory-board || \
                   "equery-${BOARD}" which chromeos-factory-board)"
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
