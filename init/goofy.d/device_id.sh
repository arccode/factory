#!/bin/sh
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Maintains '/var/factory/.device_id'. When .device_id is changed, invoke all
# scripts inside device_id/ folder.

SCRIPT="$(readlink -f "$0")"
CHANGED_DIR="${SCRIPT%.sh}_changed"
FACTORY_DIR="$(readlink -f "$(dirname "$(readlink -f "$0")")/../..")"
DATA_DIR=/var/factory

DEVICE_ID_FILE="${DATA_DIR}/.device_id"
LAST_DEVICE_ID_FILE="${DATA_DIR}/.last_device_id"

mkdir -p "${DATA_DIR}"
if [ -f "${DEVICE_ID_FILE}" ]; then
  cp -f "${DEVICE_ID_FILE}" "${LAST_DEVICE_ID_FILE}"
fi

"${FACTORY_DIR}/bin/device_id" >"${DEVICE_ID_FILE}"

if [ -f "${LAST_DEVICE_ID_FILE}" ]; then
  if [ "$(cat "${DEVICE_ID_FILE}")" != "$(cat "${LAST_DEVICE_ID_FILE}")" ]; then
    echo "Device ID changed!"
    for file in "${CHANGED_DIR}"/*.sh; do
      if [ -x "${file}" ]; then
        echo "Invoke ${file}..."
        "${file}"
      fi
    done
  fi
fi
