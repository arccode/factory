#!/bin/sh

# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Script used to show boot message.


FONT_SIZE="60"
FONT_COLOR="Green"

# Temp message file for display_boot_message.
MESSAGE_FILE="$(mktemp --tmpdir)"

: "${TTY:=/run/frecon/vt0}"

on_exit() {
  rm -f "${MESSAGE_FILE}"
}

# Prints usage help for commands usage.
usage_help() {
  echo "Usage: $0 mode

  connect_ac: Message for connecting AC.

  remove_ac: Message for removing AC.

  charging: Message when charging battery.

  discharging: Message when discharging battery.

  cutting_off: Message when running cut off commands.

  wipe: Message when wiping.

  wipe_failed: Message when wipe failed.

  cutoff_failed: Message when cut off failed.

  inform_shopfloor: Message when inform shopfloor.

  inform_shopfloor_failed: Message when inform shopfloor failed.
"
}

prepare_message() {
  local message="
    <span font=\"Noto Sans UI ${FONT_SIZE}\"
          foreground=\"${FONT_COLOR}\">"

  printf "%s\n" "${message}"
  # Append messages with newline.
  for message in "$@"; do
    printf "%s\n" "${message}"
  done
  printf "</span>"
}

has_bin() {
  type "$1" >/dev/null 2>&1
}

display_message() {
  local short_message="$1"
  shift

  # Currently in factory_install image, the fonts and assets were removed by
  # INSTALL_MASK (for smaller disk size) and the 'frecon' was provided by
  # frecon-lite, which only has access to the partition before switch_root.
  # It seems pretty hard to kill frecon-lite and restart frecon, so here we want
  # to always use figlet when running under factory install shim.

  if ! grep -qw cros_factory_install /proc/cmdline; then
    # Not in factory shim, try frecon + pango-view.
    if has_bin frecon && has_bin pango-view; then
      prepare_message "$@" >"${MESSAGE_FILE}"
      if [ "${SHOW_SPINNER}" = "true" ]; then
        SPINNER_INTERVAL=25 display_boot_message show_spinner "${MESSAGE_FILE}"
      else
        display_boot_message show_file "${MESSAGE_FILE}"
      fi
      return
    fi
  fi

  if has_bin figlet; then
    figlet "${short_message}"
    # Figlet may be not easy to read so we want to print message again.
    echo "${short_message}"
  else
    echo "${short_message}"
  fi
}

mode_connect_ac() {
  (FONT_COLOR="Red" display_message "Connect AC" \
                                    "Please Connect AC Power" \
                                    "请连接AC电源")
}

mode_remove_ac() {
  (FONT_COLOR="Red" display_message "Remove AC" \
                                    "Please Remove AC Power" \
                                    "请移除AC电源")
}

mode_charging() {
  (SHOW_SPINNER="true" display_message "Charging" \
                                       "Charging Battery..." \
                                       "正在充电...")
}

mode_discharging() {
  (SHOW_SPINNER="true" display_message "Discharging" \
                                       "Discharging Battery..." \
                                       "正在放电...")
}

mode_cutting_off() {
  (SHOW_SPINNER="true" display_message "Cutting Off" \
                                       "Cutting Off Battery" \
                                       "Please wait..." \
                                       "切断电池电源中" \
                                       "请稍候...")
}

mode_cutoff_failed() {
  (FONT_COLOR="Red" && display_message "Cutoff Failed" \
                                       "Battery Cut-off Failed" \
                                       "Please contact factory team" \
                                       "无法切断电池电源" \
                                       "请联络RD")
}

mode_wipe() {
  (SHOW_SPINNER="true" display_message "Wiping" \
                                       "Factory Wiping In Progress" \
                                       "正在进行工厂清除程序")
}

mode_wipe_failed() {
  (FONT_COLOR="Red" display_message "Wiping Failed" \
                                    "Factory Wiping Failed" \
                                    "无法进行工厂清除程序" \
                                    "请联络RD")
}

mode_inform_shopfloor() {
  (SHOW_SPINNER="true" display_message "Inform Shopfloor" \
                                       "Inform Shopfloor In Progress" \
                                       "传送资料至Shopfloor")
}

mode_inform_shopfloor_failed() {
  (FONT_COLOR="Red" display_message "Inform Shopfloor Failed" \
                                    "无法传送资料至Shopfloor" \
                                    "请联络RD")
}

main() {
  if [ $# -lt 1 ]; then
    usage_help
    exit 1
  fi
  local mode="$1"
  shift

  case "${mode}" in
    "connect_ac" | "remove_ac" | "charging" | "discharging" | \
        "cutting_off" | "cutoff_failed" | "wipe" | "wipe_failed" | \
        "inform_shopfloor" | "inform_shopfloor_failed" )
      mode_"${mode}" "$@"

      # Light up the screen if possible.
      backlight_tool --set_brightness_percent=100 2>/dev/null || true

      if [ -c "${TTY}" ]; then
        # Hides cursor and prevents console from blanking after long inactivity.
        setterm -cursor off -blank 0 -powersave off -powerdown 0 2>/dev/null \
          >>"${TTY}" || true
      fi
      ;;
    * )
      usage_help
      exit 1
      ;;
  esac
}

trap on_exit EXIT
main "$@"
