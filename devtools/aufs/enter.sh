#!/bin/bash
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$0")"
. "${SCRIPT_DIR}/common.sh"

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
TEMP_DIR="$(mktemp -d "/tmp/factory_dev_XXXXXX")"

echo "the working directory will be ${WORKING_DIR}"
mkdir -p "${WORKING_DIR}"

sudo mount -t aufs \
    -o "br=${TEMP_DIR}=rw:${OVERLAY_DIR}=ro:${FACTORY_DIR}=ro" \
    -o udba=reval none "${WORKING_DIR}" || exit $?

save_config
