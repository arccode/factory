#!/bin/bash
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

: "${SCRIPT_DIR:="$(dirname "$0")"}"

FACTORY_DIR="$(realpath "${SCRIPT_DIR}/../..")"
WORKING_DIR="$(realpath "${WORKING_DIR:-${HOME}/workspace}")"
CONFIG_FILE="${WORKING_DIR}/.aufs.config"

# Load shflags
. "${SCRIPT_DIR}/shflags"

if ( command -V tput && tput setaf 1 ) >/dev/null; then
  COLOR_RED="$(tput setaf 1; tput bold)"
  COLOR_GRN="$(tput setaf 2; tput bold)"
  COLOR_YEL="$(tput setaf 3; tput bold)"
  COLOR_BLU="$(tput setaf 4; tput bold)"
  COLOR_NOR="$(tput sgr0)"
else
  COLOR_RED=
  COLOR_GRN=
  COLOR_YEL=
  COLOR_BLU=
  COLOR_NOR=
fi

# Dump a global var into a file
# Arguments:
#   1. var_name: name of the variable to dump
#   2. file: name of the file to write
dump_var() {
  local var_name="$1"
  local file="$2"
  echo "${var_name}='${!var_name}'" >>"${file}"
}

# Save essential variables into "${CONFIG_FILE}"
# Globals:
#   CONFIG_FILE
#   FACTORY_DIR
#   OVERLAY_DIR
#   TEMP_DIR
save_config() {
  echo -n >"${CONFIG_FILE}"  # clear the file
  dump_var "FACTORY_DIR" "${CONFIG_FILE}"
  dump_var "OVERLAY_DIR" "${CONFIG_FILE}"
  dump_var "TEMP_DIR" "${CONFIG_FILE}"
}

# Load a config file
# Globals:
#   CONFIG_FILE
#   FACTORY_DIR (will be changed)
#   OVERLAY_DIR (will be changed)
#   TEMP_DIR (will be changed)
load_config() {
  source "${CONFIG_FILE}"
}

# Drop filesystem cache of "${WORKING_DIR}".
#
# This function will invoke sudo.
#
# Globals:
#   WORKING_DIR
drop_cache() {
  sudo mount -o remount "${WORKING_DIR}"
}

is_simple_mode() {
  [ "${TEMP_DIR}" == "/dev/null" ]
}
