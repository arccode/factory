#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Reads `options` file and check parameters for cut-off scripts.

# Define config default values
: ${CUTOFF_METHOD:=shutdown}
: ${CUTOFF_AC_STATE:=}
: ${CUTOFF_BATTERY_MIN_PERCENTAGE:=}
: ${CUTOFF_BATTERY_MAX_PERCENTAGE:=}
: ${CUTOFF_BATTERY_MIN_VOLTAGE:=}
: ${CUTOFF_BATTERY_MAX_VOLTAGE:=}
: ${SHOPFLOOR_URL:=}

# After calling display_wipe_message.sh to draw image with frecon, we must
# redirect text output to active terminal to display information on the screen.
: ${TTY:=/run/frecon/vt0}

# Exit as error with messages.
# Usage: die messages...
die() {
  echo "ERROR: $*" >&2
  exit 1
}

# Usage: lsbval path-to-lsb-file key default
# Returns the value for the given lsb-release file variable.
lsbval() {
  local lsbfile="$1"
  local key="$2"
  local default="$3"
  local value="$(sed -n "s/^\s*${key}\s*=\s*\(.*\)\s*$/=\1/p" "${lsbfile}")"
  if [ -n "${value}" ]; then
    echo "${value#=}"
  else
    echo "${default}"
  fi
}

# Try to find a real working TTY.
options_find_tty() {
  local tty
  for tty in "${TTY}" /dev/tty1 /dev/tty /dev/console /dev/null; do
    # Not only check the TTY exists, but also check piping works.
    if [ -c "${tty}" ] && echo "" >"${tty}" 2>&1; then
      TTY="${tty}"
      break
    fi
  done
  echo "Selected TTY: ${TTY}"
  export TTY
}

# Try to read from config file. This file should be using same format that
# /etc/lsb-release is using and friendly for sh to process, or a JSON file.
# Usage: load_options_file <FILE>
options_load_file() {
  local file="$1"
  local key value
  if [ -f "${file}" ]; then
    if [ "${file%.json}" != "${file}" ] &&
         python -c "import jsonschema" >/dev/null 2>&1; then
      echo "Checking JSON schema for file ${file}..."
      python -c "import jsonschema; import json; jsonschema.validate(
        json.load(open('${file}')),
        json.load(open('$(dirname "$(readlink -f "$0")")/cutoff.schema.json')))"
    fi
    echo "Loading options from file ${file}..."
    for key in CUTOFF_METHOD CUTOFF_AC_STATE \
        CUTOFF_BATTERY_MIN_PERCENTAGE CUTOFF_BATTERY_MAX_PERCENTAGE \
        CUTOFF_BATTERY_MIN_VOLTAGE CUTOFF_BATTERY_MAX_VOLTAGE \
        SHOPFLOOR_URL TTY; do
      if [ "${file%.json}" != "${file}" ]; then
        # "jq -n -f" allows more flexible JSON, for example keys without quotes
        # or comments started with #.
        value="$(jq -n -f "${file}" | jq -r ".${key}")"
        if [ "${value}" = "null" ]; then
          value="$(eval echo "\${${key}}")"
        fi
      else
        value="$(lsbval "${file}" ${key} "$(eval echo "\${${key}}")")"
      fi
      eval ${key}='${value}'
    done
  fi
}

# Check if an option in number type.
# Usage: option_check_range <value> <value_name> <range-min> <range-max>
option_check_range() {
  local value="$1"
  local value_name="$2"
  local value_min="$3"
  local value_max="$4"
  if [ -z "${value}" ]; then
    return 0
  fi
  if [ "${value}" -ge "${value_min}" -a "${value}" -le "${value_max}" ]; then
    return 0
  fi
  die "Option ${value_name} not in range [${value_min},${value_max}]: ${value}"
}

# Check if an option is in known set.
# Usage: option_check_set <value> <value_name> <valid_values...>
option_check_set() {
  local value="$1"
  local value_name="$2"
  shift
  shift
  local valid_values="$*"
  if [ -z "${value}" ]; then
    return 0
  fi
  while [ "$#" -gt 0 ]; do
    if [ "${value}" = "$1" ]; then
      return 0
    fi
    shift
  done
  die "Option ${value_name} is not one of [${valid_values}]: ${valud}"
}

# Checks known option values.
# Usage: options_check_values
options_check_values() {
  option_check_set "${CUTOFF_METHOD}" CUTOFF_METHOD \
    shutdown reboot battery_cutoff ectool_cutoff
  option_check_set "${CUTOFF_AC_STATE}" CUTOFF_AC_STATE \
    connect_ac remove_ac
  option_check_range "${CUTOFF_BATTERY_MIN_PERCENTAGE}" \
    CUTOFF_BATTERY_MIN_PERCENTAGE 0 100
  option_check_range "${CUTOFF_BATTERY_MAX_PERCENTAGE}" \
    CUTOFF_BATTERY_MAX_PERCENTAGE 0 100
  if [ ! -e "${TTY}" ]; then
    die "Cannot find valid TTY in ${TTY}."
  fi
  echo "Active Configuration:"
  echo "---------------------"
  echo "CUTOFF_METHOD=${CUTOFF_METHOD}"
  echo "CUTOFF_AC_STATE=${CUTOFF_AC_STATE}"
  echo "CUTOFF_BATTERY_MIN_PERCENTAGE=${CUTOFF_BATTERY_MIN_PERCENTAGE}"
  echo "CUTOFF_BATTERY_MAX_PERCENTAGE=${CUTOFF_BATTERY_MAX_PERCENTAGE}"
  echo "CUTOFF_BATTERY_MIN_VOLTAGE=${CUTOFF_BATTERY_MIN_VOLTAGE}"
  echo "CUTOFF_BATTERY_MAX_VOLTAGE=${CUTOFF_BATTERY_MAX_VOLTAGE}"
  echo "SHOPFLOOR_URL=${SHOPFLOOR_URL}"
  echo "TTY=${TTY}"
  echo "---------------------"
}

# Provides common usage help.
# Usage: options_usage_help
options_usage_help() {
  echo "Usage: $0
    [--method shutdown|reboot|battery_cutoff|ectool_cutoff]
    [--check-ac connect_ac|remove_ac]
    [--min-battery-percent <minimum battery percentage>]
    [--max-battery-percent <maximum battery percentage>]
    [--min-battery-voltage <minimum battery voltage>]
    [--max-battery-voltage <maximum battery voltage>]
    [--shopfloor <shopfloor_url]
    [--tty <tty_path>]
    "
  exit 1
}

# Parses options from command line.
# Usage: options_parse_command_line "$@"
options_parse_command_line() {
  while [ "$#" -ge 1 ]; do
    case "$1" in
      --method )
        shift
        CUTOFF_METHOD="$1"
        ;;
      --check-ac )
        shift
        CUTOFF_AC_STATE="$1"
        ;;
      --min-battery-percent )
        shift
        CUTOFF_BATTERY_MIN_PERCENTAGE="$1"
        ;;
      --max-battery-percent )
        shift
        CUTOFF_BATTERY_MAX_PERCENTAGE="$1"
        ;;
      --min-battery-voltage )
        shift
        CUTOFF_BATTERY_MIN_VOLTAGE="$1"
        ;;
      --max-battery-voltage )
        shift
        CUTOFF_BATTERY_MAX_VOLTAGE="$1"
        ;;
      --shopfloor )
        shift
        SHOPFLOOR_URL="$1"
        ;;
      --tty )
        shift
        TTY="$1"
        ;;
      * )
        options_usage_help "$1"
        ;;
    esac
    shift
  done
}

# Loads all known default config files.
# Usage: options_load_all_default_files
options_load_all_default_files() {
  local cutoff_dir="$(dirname "$(readlink -f "$0")")"

  # Default LSB config file.
  options_load_file "${cutoff_dir}/cutoff.conf"

  # Board-specific JSON config (used by Finalize / in-place-wiping).
  options_load_file "${cutoff_dir}/../../py/config/cutoff.json"

  # Board-specific JSON config (used by factory shim, copied from py/config).
  options_load_file "${cutoff_dir}/cutoff.json"

  # Manually modified LSB config on factory shim.
  options_load_file "/mnt/stateful_partition/dev_image/etc/lsb-factory"
}

options_load_all_default_files

# Allow debugging options quickly.
if [ "$(basename "$0")" = "options.sh" ]; then
  options_check_values
fi
