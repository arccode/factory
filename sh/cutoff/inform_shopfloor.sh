#!/bin/sh
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# This script makes shopfloor call to inform shopfloor server. It can be used
# after factory wiping (in-place wiping tmpfs) or after factory reset
# (in factory reset shim) to inform shopfloor the operation is completed.

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
DISPLAY_MESSAGE="${SCRIPT_DIR}/display_wipe_message.sh"
. "${SCRIPT_DIR}/options.sh"

GENERATE_FINALIZE_REQUEST="${SCRIPT_DIR}/generate_finalize_request.sh"

POST_FILE="$(mktemp --tmpdir)"

on_exit() {
  rm -f "${POST_FILE}"
}

die_with_error_message() {
  "${DISPLAY_MESSAGE}" "inform_shopfloor_failed"

  # In factory install shim, we need to reset tty1 to show message in currect
  # way.
  stty -F "${TTY}" sane
  echo "$@" > "${TTY}"
  # Stop here to show error message on the screen.
  read
}

usage_help() {
  echo "Usage: $0 SHOPFLOOR_URL <POST_FILE | factory_reset | factory_wipe>"
}

post_to_shopfloor() {
  local shopfloor_url="$1"
  local post_file="$2"
  local response=""

  while true; do
    echo "Sending data to shopfloor..." >"${TTY}"
    if response=$(wget -T 30 --tries 1 -q --header='Content-Type: text/xml' \
        --post-file="${post_file}" -O - "${shopfloor_url}"); then
      if ! echo "${response}" | grep -q "fault"; then
        return
      else
        echo "Shopfloor call failed with response ${response}" >"${TTY}"
      fi
    else
      echo "Cannot connect to server ${shopfloor_url}." >"${TTY}"
    fi
    echo "Retry in 10s..." >"${TTY}"
    sleep 10
    # Clear screen.
    printf "\033c" >"${TTY}"
  done
}

main() {
  if [ $# -ne 2 ]; then
    usage_help
    exit 1
  fi
  export TTY  # for display_wipe_message to use same TTY settings.

  local shopfloor_url="$1"
  if [ -z "${shopfloor_url}" ]; then
    shopfloor_url="${SHOPFLOOR_URL}"
  fi

  "${DISPLAY_MESSAGE}" "inform_shopfloor"

  case "$2" in
    factory_reset|factory_wipe )
      if ! "${GENERATE_FINALIZE_REQUEST}" "$2" >"${POST_FILE}"; then
        local err=""
        err="$(cat ${POST_FILE})"
        die_with_error_message "Failed to generate request: ${err}"
      fi
      post_to_shopfloor "${shopfloor_url}" "${POST_FILE}"
      ;;
    * )
      if [ -f "$2" ]; then
        wait_for_ethernet
        post_to_shopfloor "${shopfloor_url}" "$2"
      else
        usage_help
        exit 1
      fi
      ;;
  esac
}

trap on_exit EXIT
main "$@"
