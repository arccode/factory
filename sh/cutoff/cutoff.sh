#!/bin/sh

# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script controls battery power level and performs required battery
# cutoff protection by sending commands to EC with ectool.

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
DISPLAY_MESSAGE="${SCRIPT_DIR}/display_wipe_message.sh"
. "${SCRIPT_DIR}/options.sh"

reset_activate_date() {
  activate_date --clean
}

# Resets the recovery_count to 0 in RW_VPD.
reset_recovery_count() {
  echo "Checking recovery_count in RW VPD..."
  if [ -n "$(vpd -i RW_VPD -g recovery_count 2>/dev/null)" ]; then
    echo "Deleting recovery_count from VPD."
    vpd -i RW_VPD -d "recovery_count"
  else
    echo "OK: no recovery_count found."
  fi
}

has_battery() {
  ( type ectool && ectool battery ) >/dev/null 2>&1
}

get_battery_percentage() {
  local full="" current=""
  full="$(ectool battery 2>/dev/null |
    awk '/Last full charge/ {print int($4)}')"
  current="$(ectool battery 2>/dev/null |
    awk '/Remaining capacity/ {print int($3)}')"
  echo $((current * 100 / full))
}

get_battery_voltage() {
  ectool battery 2>/dev/null | awk '/Present voltage/ {print int($3)}'
}

is_ac_present() {
  ectool battery | grep -q AC_PRESENT
}

require_ac() {
  if ! is_ac_present; then
    "${DISPLAY_MESSAGE}" "connect_ac"
    while ! is_ac_present; do
      sleep 0.5
    done
  fi
}

require_remove_ac() {
  if is_ac_present; then
    "${DISPLAY_MESSAGE}" "remove_ac"
    while is_ac_present; do
      sleep 0.5
    done
  fi
}

charge_control() {
  ectool chargecontrol "$1" >/dev/null
}

run_stressapptest() {
  local VERY_LONG_TIME="1000000"
  # It may crash the system if it use too much memory on Factory Shim.
  stressapptest -M 128 -s "${VERY_LONG_TIME}" >/dev/null &
  echo "$!"
}

check_battery_value() {
  local min_battery_value="$1" max_battery_value="$2"
  local get_value_cmd="$3"
  local battery_value=""
  local prev_battery_value=""
  local stressapptest_pid=""

  battery_value="$(${get_value_cmd})"

  if [ -n "$min_battery_value" ] &&
     [ "$battery_value" -lt "$min_battery_value" ]; then
    require_ac
    charge_control "normal"
    ${DISPLAY_MESSAGE} "charging"

    # Wait for battery to charge to min_battery_value
    prev_battery_value="-1"
    # Print a new line before and after showing battery info.
    echo ""
    while [ "$battery_value" -lt "$min_battery_value" ]; do
      # Only print battery info when it changes.
      if [ "$battery_value" -ne "$prev_battery_value" ]; then
        # Keep printing battery information in the same line.
        printf '\rcurrent: %s, target: %s' \
            "$battery_value" "$min_battery_value" >"${TTY}"
        prev_battery_value="$battery_value"
      fi
      sleep 1
      battery_value="$(${get_value_cmd})"
    done
    echo ""
  fi

  if [ -n "$max_battery_value" ] &&
     [ "$battery_value" -gt "$max_battery_value" ]; then
    # Use stressapptest to discharge battery faster
    stressapptest_pid="$(run_stressapptest)"
    charge_control "discharge"
    ${DISPLAY_MESSAGE} "discharging"

    # Wait for battery to discharge to max_battery_value
    prev_battery_value="-1"
    # Print a new line before and after showing battery info.
    echo ""
    while [ "$battery_value" -gt "$max_battery_value" ]; do
      # Only print battery info when it changes.
      if [ "$battery_value" -ne "$prev_battery_value" ]; then
        # Keep printing battery information in the same line.
        printf '\rcurrent: %s, target: %s' \
            "$battery_value" "$max_battery_value" >"${TTY}"
        prev_battery_value="$battery_value"
      fi
      sleep 1
      battery_value="$(${get_value_cmd})"
    done
    echo ""
  fi

  charge_control "idle"
  if [ -n "$stressapptest_pid" ]; then
    kill -9 "$stressapptest_pid"
  fi
}

check_ac_state() {
  local ac_state="$1"
  if [ "$ac_state" = "connect_ac" ]; then
    require_ac
  elif [ "$ac_state" = "remove_ac" ]; then
    require_remove_ac
  fi
}

main() {
  options_find_tty

  local key
  options_parse_command_line "$@"
  options_check_values

  reset_activate_date
  reset_recovery_count

  if has_battery; then
    # Needed by 'ectool battery'.
    mkdir -p /var/lib/power_manager
    modprobe i2c_dev || true
    if [ -n "$CUTOFF_BATTERY_MIN_PERCENTAGE" ] || \
       [ -n "$CUTOFF_BATTERY_MAX_PERCENTAGE" ]; then
      check_battery_value \
        "$CUTOFF_BATTERY_MIN_PERCENTAGE" "$CUTOFF_BATTERY_MAX_PERCENTAGE" \
        "get_battery_percentage"
    fi
    if [ -n "$CUTOFF_BATTERY_MIN_VOLTAGE" ] || \
       [ -n "$CUTOFF_BATTERY_MAX_VOLTAGE" ]; then
      check_battery_value \
        "$CUTOFF_BATTERY_MIN_VOLTAGE" "$CUTOFF_BATTERY_MAX_VOLTAGE" \
        "get_battery_voltage"
    fi
  fi

  # Ask operator to plug or unplug AC before doing cut off.
  check_ac_state "$CUTOFF_AC_STATE"

  $DISPLAY_MESSAGE "cutting_off"

  # TODO (shunhsingou): In bug
  # https://bugs.chromium.org/p/chromium/issues/detail?id=589677, small amount
  # of devices fail to do cut off in factory. This may be caused by unstable
  # ectool, or shutdown fail in the tmpfs. Here we add more retries for
  # solving this problem. Remove the retry when finding the root cause.
  for i in $(seq 5)
  do
    case "$CUTOFF_METHOD" in
      reboot)
        reboot
      ;;
      ectool_cutoff)
        # If virtual dev mode was enabled, ectool cutoff will leave the device
        # in developer mode. Unfortunately we can't check that because TPM
        # service was not running, and tpm_nvread won't work.
        ectool batterycutoff at-shutdown && shutdown -h now
      ;;
      battery_cutoff)
        crossystem battery_cutoff_request=1 && sleep 3 && reboot
      ;;
      shutdown | *)
        # By default we shutdown the device without doing anything.
        shutdown -h now
    esac
    sleep 15
  done

  $DISPLAY_MESSAGE "cutoff_failed"
  sleep 1d
  exit 1
}

main "$@"
