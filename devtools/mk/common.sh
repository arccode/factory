# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# To use this file, add the following two lines in your script:
#  SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
#  . "${SCRIPT_DIR}/common.sh" || exit 1
# And then invoke 'mk_success' in end of you main().

COMMON_TEMP_OBJECTS=()

error() {
  echo "$(tput bold)$(tput setaf 1)ERROR: $*$(tput sgr0)" >&2 2>/dev/null
}

info() {
  echo "$(tput bold)$(tput setaf 2)INFO: $*$(tput sgr0)" >&2 2>/dev/null
}

warn() {
  echo "$(tput bold)$(tput setaf 3)WARN: $*$(tput sgr0)" >&2 2>/dev/null
}

add_temp() {
  COMMON_TEMP_OBJECTS+=("$@")
}

del_all_temp() {
  local object
  for object in "${COMMON_TEMP_OBJECTS[@]}"; do
    rm -rf "${object}" 2>/dev/null
  done
  COMMON_TEMP_OBJECTS=()
}

die() {
  local exit_value="$?"
  trap - EXIT
  if [ -z "$*" ]; then
    error "Unexpected failure (exit code: ${exit_value}). Abort."
  else
    error "$*"
  fi
  [ "${exit_value}" = "0" ] && exit_value=1
  on_exit "${exit_value}"
}

on_exit() {
  local exit_value="$?"
  if [ "$#" -eq 1 ]; then
    exit_value="$1"
  fi
  del_all_temp
  exit "${exit_value}"
}

mk_success() {
  trap on_exit EXIT
}

# Set program to alert on abort.
set -e
trap die EXIT
