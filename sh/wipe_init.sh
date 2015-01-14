#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script mounts stateful partition, reads options in stateful reset file
# to invoke clobber-state for factory wiping.


# =====================================================================
# Set up logging
LOG_FILE="/tmp/wipe_init.log"

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

# Appends messages with newline.
split_messages() {
  local message=""
  for message in "$@"; do
    printf "${message}\n"
  done
}

display_message() {
  local text_file="$(mktemp)"
  split_messages "$@" >"${text_file}"
  display_boot_message show_file "${text_file}"
}

die() {
  echo "ERROR: $*"
  stop_and_save_logging

  display_message "Factory wipe failed in wipe_init" \
                  "Please contact engineer for help."

  exit 1
}

# Dumps each command to "${LOG_FILE}".
set -xe
exec >"${LOG_FILE}" 2>&1

# This script never exits under normal conditions. Traps all unexpected errors.
trap die EXIT

# ======================================================================
# Constants

STATE_PATH="/mnt/stateful_partition"

# ======================================================================
# Global variables

FACTORY_ROOT_DEV="$1"
STATE_DEV=${FACTORY_ROOT_DEV%[0-9]*}1
WIPE_MESSAGE="/usr/local/factory/misc/wipe_message.png"

ROOT_DISK="$2"
WIPE_ARGS="$3"

# ======================================================================
# Helper functions

start_wipe() {
  local release_root_dev=""
  release_root_dev=$(echo "${FACTORY_ROOT_DEV}" | tr '35' '53')

  ROOT_DEV="${release_root_dev}" ROOT_DISK="${ROOT_DISK}" \
    FACTORY_RETURN_AFTER_WIPING="YES" clobber-state "${WIPE_ARGS}"
  mv -f "/tmp/clobber-state.log" "${STATE_PATH}/unencrypted/clobber-state.log"

  enable_release_partition "${release_root_dev}"

  # TODO(shunhsingou): need to inform shopfloor here.
  # TODO(shunhsingou): enable more wiping options,
  # e.g., battery cutoff, shutdown, etc.
  trap - EXIT
  shutdown -r now
  sleep 1d  # Wait for shutdown
}

# ======================================================================
# Main function

main() {
  display_boot_message show_spinner "${WIPE_MESSAGE}"
  start_wipe
}

main "$@"
