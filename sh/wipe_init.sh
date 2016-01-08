#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script invokes clobber-state for factory wiping, and then invokes
# battery_cutoff.sh
#

# ======================================================================
# Constants

STATE_PATH="/mnt/stateful_partition"

BATTERY_CUTOFF="/usr/local/factory/sh/battery_cutoff.sh"
DISPLAY_MESSAGE="/usr/local/factory/sh/display_wipe_message.sh"
ENABLE_RELEASE_PARTITION="/usr/local/factory/bin/enable_release_partition"
INFORM_SHOPFLOOR="/usr/local/factory/sh/inform_shopfloor.sh"

LOG_FILE="/tmp/wipe_init.log"

# =====================================================================
# Set up logging

stop_and_save_logging() {
  # Stop appending to the log and preserve it.
  exec >/dev/null 2>&1

  # If stateful partition is already unmounted, mount it before save log
  # to stateful partition.
  if ! mount | awk '{print $3}' | grep -q "^${STATE_PATH}$"; then
    mount -t ext4 "${STATE_DEV}" "${STATE_PATH}"
  fi
  mv -f "${LOG_FILE}" "${STATE_PATH}"/unencrypted/"$(basename "${LOG_FILE}")"
  sync && sleep 3
}

die() {
  echo "ERROR: $*"
  stop_and_save_logging

  ${DISPLAY_MESSAGE} wipe_failed

  exit 1
}

# Dumps each command to "${LOG_FILE}".
set -xe
exec >"${LOG_FILE}" 2>&1

# This script never exits under normal conditions. Traps all unexpected errors.
trap die EXIT

# ======================================================================
# Global variables

FACTORY_ROOT_DEV="$1"
STATE_DEV=${FACTORY_ROOT_DEV%[0-9]*}1

ROOT_DISK="$2"
WIPE_ARGS="$3"
CUTOFF_ARGS="$4"
SHOPFLOOR_URL="$5"

# ======================================================================
# Helper functions

start_wipe() {
  local release_root_dev=""
  release_root_dev=$(echo "${FACTORY_ROOT_DEV}" | tr '35' '53')

  ROOT_DEV="${release_root_dev}" ROOT_DISK="${ROOT_DISK}" \
    FACTORY_RETURN_AFTER_WIPING="YES" clobber-state "${WIPE_ARGS}"
  mv -f "/tmp/clobber-state.log" "${STATE_PATH}/unencrypted/clobber-state.log"

  # Remove developer flag, which is created by clobber-state after wiping.
  rm -f "${STATE_PATH}/.developer_mode"

  "${ENABLE_RELEASE_PARTITION}" "${release_root_dev}"

  if [ -n "${SHOPFLOOR_URL}" ]; then
    "${INFORM_SHOPFLOOR}" "${SHOPFLOOR_URL}" "factory_wipe"
  fi

  trap - EXIT
  "${BATTERY_CUTOFF}" ${CUTOFF_ARGS}

  # Should not reach here.
  sleep 1d
}

# ======================================================================
# Main function

main() {
  "${DISPLAY_MESSAGE}" wipe
  start_wipe
}

main "$@"
