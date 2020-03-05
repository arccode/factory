#!/bin/sh

# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script controls battery power level and performs required battery
# cutoff protection by sending commands to EC with ectool.

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
DISPLAY_MESSAGE="${SCRIPT_DIR}/display_wipe_message.sh"
. "${SCRIPT_DIR}/options.sh"
EC_PRESENT=0
ECTOOL_BATTERY_SUPPORT=0
POWER_SUPPLY_PATH="/sys/class/power_supply"

cutoff_failed() {
  "${DISPLAY_MESSAGE}" "cutoff_failed"
  sleep 1d
  exit 1
}

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

test_ec_flash_presence() {
  # If "flashrom -p ec --flash-size" command succeeds (returns 0),
  # then EC flash chip is present in system. Otherwise, assume EC flash is not
  # present or supported.
  if flashrom -p ec --flash-size >/dev/null 2>&1; then
    EC_PRESENT=1
  else
    EC_PRESENT=0
  fi
}

test_ectool_battery_support() {
  # Check if "ectool battery" works
  if [ "${EC_PRESENT}" -eq 1 ] && ectool battery >/dev/null 2>&1; then
    ECTOOL_BATTERY_SUPPORT=1
  else
    ECTOOL_BATTERY_SUPPORT=0
  fi
}

find_battery_path() {
  local battery_path=""
  for power_supply in "${POWER_SUPPLY_PATH}"/*; do
    if [ -f "${power_supply}/type" ] &&
       [ "$(cat "${power_supply}/type")" = "Battery" ] &&
       [ -f "${power_supply}/present" ] &&
       [ "$(cat "${power_supply}/present")" != "0" ] &&
       [ -f "${power_supply}/status" ] &&
       [ "$(cat "${power_supply}/status")" != "Unknown" ] &&
       [ -f "${power_supply}/voltage_now" ] &&
       [ -f "${power_supply}/charge_full" ] &&
       [ -f "${power_supply}/charge_now" ]; then
      battery_path="${power_supply}"
      break
    fi
  done
  echo "${battery_path}"
}

get_battery_percentage() {
  local battery_path="$1"
  local full
  local current
  full="$(cat "${battery_path}/charge_full")" || return $?
  current="$(cat "${battery_path}/charge_now")" || return $?
  echo "$((current * 100 / full))"
}

get_battery_voltage() {
  local battery_path="$1"
  local battery_voltage
  battery_voltage="$(cat "${battery_path}/voltage_now")" || return $?
  echo "$((battery_voltage / 1000))"
}

get_ectool_battery_percentage() {
  [ "${ECTOOL_BATTERY_SUPPORT}" -eq 1 ] || return 1

  local battery_info
  local full
  local current
  battery_info="$(ectool battery)"
  full="$(echo "${battery_info}" |
    sed -n -r 's/.*Design capacity:* *([0-9]+) mAh.*/\1/p')"
  current="$(echo "${battery_info}" |
    sed -n -r 's/.*Remaining capacity *([0-9]+) mAh.*/\1/p')"
  [ -n "${full}" ] || return 1
  [ -n "${current}" ] || return 1

  echo "$((current * 100 / full))"
}

get_ectool_battery_voltage() {
  [ "${ECTOOL_BATTERY_SUPPORT}" -eq 1 ] || return 1

  local battery_info
  local voltage
  battery_info="$(ectool battery)"
  voltage="$(echo "${battery_info}" |
    sed -n -r 's/.*Present voltage *([0-9]+) mV.*/\1/p')"
  [ -n "${voltage}" ] || return 1

  echo "${voltage}"
}

find_ac_path() {
  local ac_path=""
  for power_supply in "${POWER_SUPPLY_PATH}"/*; do
    if [ -f "${power_supply}/type" ] &&
       [ "$(cat "${power_supply}/type")" != "Battery" ] &&
       [ -f "${power_supply}/online" ] &&
       [ "$(cat "${power_supply}/online")" != "0" ]; then
      ac_path="${power_supply}"
      break
    fi
  done
  echo "${ac_path}"
}

require_ac() {
  if [ -z "$(find_ac_path)" ]; then
    "${DISPLAY_MESSAGE}" "connect_ac"
    while [ -z "$(find_ac_path)" ]; do
      sleep 0.5
    done
  fi
}

require_remove_ac() {
  if [ -n "$(find_ac_path)" ]; then
    "${DISPLAY_MESSAGE}" "remove_ac"
    while [ -n "$(find_ac_path)" ]; do
      sleep 0.5
    done
  fi
}

charge_control() {
  if [ "${EC_PRESENT}" = "1" ]; then
    ectool chargecontrol "$1" >/dev/null
  else
    echo "Not support charge_control without EC."
  fi
}

run_stressapptest() {
  local VERY_LONG_TIME=1000000
  # It may crash the system if it use too much memory on Factory Shim.
  stressapptest -M 128 -s "${VERY_LONG_TIME}" >/dev/null &
  echo "$!"
}

check_battery_value() {
  local min_battery_value="$1" max_battery_value="$2"
  local get_value_cmd="$3"
  local battery_path="$4"
  local battery_value=""
  local prev_battery_value=""
  local stressapptest_pid=""

  battery_value="$(${get_value_cmd} "${battery_path}")" || return $?

  if [ -n "${min_battery_value}" ] &&
     [ "${battery_value}" -lt "${min_battery_value}" ]; then
    require_ac
    charge_control "normal"
    "${DISPLAY_MESSAGE}" "charging"

    # Wait for battery to charge to min_battery_value
    prev_battery_value="-1"
    # Print a new line before and after showing battery info.
    echo ""
    while [ "${battery_value}" -lt "${min_battery_value}" ]; do
      # Only print battery info when it changes.
      if [ "${battery_value}" -ne "${prev_battery_value}" ]; then
        # Keep printing battery information in the same line.
        printf '\rcurrent: %s, target: %s' \
            "${battery_value}" "${min_battery_value}" >"${TTY}"
        prev_battery_value="${battery_value}"
      fi
      sleep 1
      battery_value="$(${get_value_cmd} "${battery_path}")" || return $?
    done
    echo ""
  fi

  if [ -n "${max_battery_value}" ] &&
     [ "${battery_value}" -gt "${max_battery_value}" ]; then
    # Use stressapptest to discharge battery faster
    stressapptest_pid="$(run_stressapptest)"
    charge_control "discharge"
    "${DISPLAY_MESSAGE}" "discharging"

    # Wait for battery to discharge to max_battery_value
    prev_battery_value="-1"
    # Print a new line before and after showing battery info.
    echo ""
    while [ "${battery_value}" -gt "${max_battery_value}" ]; do
      # Only print battery info when it changes.
      if [ "${battery_value}" -ne "${prev_battery_value}" ]; then
        # Keep printing battery information in the same line.
        printf '\rcurrent: %s, target: %s' \
            "${battery_value}" "${max_battery_value}" >"${TTY}"
        prev_battery_value="${battery_value}"
      fi
      sleep 1
      battery_value="$(${get_value_cmd} "${battery_path}")" || return $?
    done
    echo ""
  fi

  if [ -n "${stressapptest_pid}" ]; then
    kill -9 "${stressapptest_pid}"
  fi
}

check_ac_state() {
  local ac_state="$1"
  if [ "${ac_state}" = "connect_ac" ]; then
    require_ac
  elif [ "${ac_state}" = "remove_ac" ]; then
    require_remove_ac
  fi
}

main() {
  options_find_tty

  options_parse_command_line "$@"
  options_check_values

  reset_activate_date
  reset_recovery_count

  test_ec_flash_presence
  test_ectool_battery_support

  local battery_path
  battery_path="$(find_battery_path)"
  if [ -n "${battery_path}" ]; then
    echo "Battery found in ${battery_path}."
    # Needed by 'ectool battery'.
    mkdir -p /var/lib/power_manager
    modprobe i2c_dev || true
    if [ -n "${CUTOFF_BATTERY_MIN_PERCENTAGE}" ] ||
       [ -n "${CUTOFF_BATTERY_MAX_PERCENTAGE}" ]; then
      check_battery_value \
        "${CUTOFF_BATTERY_MIN_PERCENTAGE}" "${CUTOFF_BATTERY_MAX_PERCENTAGE}" \
        "get_ectool_battery_percentage" "" ||
      check_battery_value \
        "${CUTOFF_BATTERY_MIN_PERCENTAGE}" "${CUTOFF_BATTERY_MAX_PERCENTAGE}" \
        "get_battery_percentage" "${battery_path}" ||
      cutoff_failed
    fi
    if [ -n "${CUTOFF_BATTERY_MIN_VOLTAGE}" ] ||
       [ -n "${CUTOFF_BATTERY_MAX_VOLTAGE}" ]; then
      check_battery_value \
        "${CUTOFF_BATTERY_MIN_VOLTAGE}" "${CUTOFF_BATTERY_MAX_VOLTAGE}" \
        "get_ectool_battery_voltage" "" ||
      check_battery_value \
        "${CUTOFF_BATTERY_MIN_VOLTAGE}" "${CUTOFF_BATTERY_MAX_VOLTAGE}" \
        "get_battery_voltage" "${battery_path}" ||
      cutoff_failed
    fi

    # Ask operator to plug or unplug AC before doing cut off.
    # The operator might not do this immediately, so we set the charge status to
    # idle to keep the charge percentage stable, and set back to normal just
    # before doing cutting off.
    charge_control "idle"
    check_ac_state "${CUTOFF_AC_STATE}"
    charge_control "normal"
  else
    echo "Battery not found."
  fi

  $DISPLAY_MESSAGE "cutting_off"

  # TODO (shunhsingou): In bug
  # https://bugs.chromium.org/p/chromium/issues/detail?id=589677, small amount
  # of devices fail to do cut off in factory. This may be caused by unstable
  # ectool, or shutdown fail in the tmpfs. Here we add more retries for
  # solving this problem. Remove the retry when finding the root cause.
  for _ in $(seq 5)
  do
    case "${CUTOFF_METHOD}" in
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
      ec_hibernate)
        ectool reboot_ec hibernate at-shutdown && shutdown -h now
      ;;
      shutdown | *)
        # By default we shutdown the device without doing anything.
        shutdown -h now
    esac
    sleep 15
  done

  cutoff_failed
}

main "$@"
