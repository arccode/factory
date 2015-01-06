#!/bin/bash
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

set -e

. /usr/local/factory/sh/common.sh

FACTORY="$(dirname "$(dirname "$(readlink -f "$0")")")"
FACTORY_LOG_FILE=/var/factory/log/factory.log
SESSION_LOG_FILE=/var/log/factory_session.log
INTERACTIVE_CONSOLES=""
LOG_PROCESSES=""

BOARD_SETUP=("$FACTORY/board/board_setup_factory.sh"
             "$FACTORY/custom/board_setup_factory.sh")

# Put '/usr/local/factory/bin' at the head of PATH so that Goofy doesn't need to
# specify full path name when running factory binaries.
export PATH="/usr/local/factory/bin:${PATH}"

# Default args for Goofy.
GOOFY_ARGS=""
PRESENTER_ARGS=""

# Ports used by goofy
GOOFY_UI_PORT="4012"
GOOFY_LINK_PORTS="4020 4021 4022 4023"

# Default implementation for factory_setup (no-op).  May be overriden
# by board_setup_factory.sh.
factory_setup() {
    true
}

# Clean up when error happens.
on_error() {
  local pid
  # Try to show console because stopping UI may take a while.
  show_interactive_console
  stop -n ui >/dev/null 2>&1 || true
  for pid in ${LOG_PROCESSES}; do
    kill -9 "${pid}" &
  done
  # Show console again because stopping UI may change active console.
  show_interactive_console
}

# Initialize output system (create logs and redirect output).
init_output() {
  echo "Redirecting output to ${SESSION_LOG_FILE}"
  exec >"${SESSION_LOG_FILE}" 2>&1
  echo "New factory session: $(date +'%Y%m%d %H:%M:%s')"

  # When VT is available, TTYs were reserved as:
  #  1 - UI (Chrome or X)
  #  2 - getty (login)
  #  3 - tail -f /var/log/factory.log
  # So for Goofy session, we want to print the logs in following order:
  #  - /dev/tty4 if available (Systems with VT)
  #  - /dev/console if available
  local tty
  for tty in /dev/tty4 /dev/console $(tty); do
    if [ -c "${tty}" ] && (echo "" >>"${tty}") 2>/dev/null; then
      tail -f "${SESSION_LOG_FILE}" >>"${tty}" &
      LOG_PROCESSES="${LOG_PROCESSES} $!"
      INTERACTIVE_CONSOLES="${INTERACTIVE_CONSOLES} ${tty}"
    fi
  done
  trap on_error EXIT

  # This should already exist, but just in case...
  mkdir -p "$(dirname "$FACTORY_LOG_FILE")"
  ln -sf "$FACTORY_LOG_FILE" /var/log
}

# Try to show the interactive console if available.
show_interactive_console() {
  local tty
  local vt_index
  for tty in ${INTERACTIVE_CONSOLES}; do
    vt_index="${tty#/dev/tty}"
    if [ "${vt_index}" = "${tty}" ]; then
      continue
    fi
    chvt "${vt_index}" && return || true
  done
}

# Load board-specific parameters, if any.
load_setup() {
  for f in "${BOARD_SETUP[@]}"; do
    if [ -s $f ]; then
      echo "Loading board-specific parameters $f..."
      . $f
      break
    fi
  done

  if [[ -f ${AUTOMATION_MODE_TAG_FILE} ]]; then
    local mode="$(cat ${AUTOMATION_MODE_TAG_FILE})"
    if [[ -n "${mode}" ]]; then
      echo "Enable factory test automation with mode: ${mode}"
      GOOFY_ARGS="${GOOFY_ARGS} --automation-mode=${mode}"
    fi
    if [[ -f ${STOP_AUTO_RUN_ON_START_TAG_FILE} ]]; then
      echo "Suppress test list auto-run on start"
      GOOFY_ARGS="${GOOFY_ARGS} --no-auto-run-on-start"
    fi
  fi

  factory_setup
}

# Checks disk usage and abort if running out of disk space.
check_disk_usage() {
  # Show error in red
  printf "\e[1;31m"
  if "$FACTORY/bin/disk_space"; then
    printf "\e[0m"
    return
  fi
  echo "
  /-\_     ___                   ___           --------+ +--------|
  \_  \    / |______     ________| |_________  |+----+ | | +----+ |
    \  \  /  _____. \    | .______________. |  ||    | | | |    | |
     \_/ /  /     | |    | |              | |  ||____| | | |____| |
         | |      | |    | |              | |  | ____  | |  ____  |
         | |      | |    |_|  /-|   |-\_  |_|  ||    | | | |    | |
 .--.   _|/     __| |       _/  /   \_  \_     ||    | | | |    | |
  \  \ /_ |    /    /     _/  _/      \   \    ||____| | | |____| |
   \--\  \/    \___/     /   /         \_  \   | ______| |______  |
                         ---/            \  |  ||               | |
         ____________                     \/   ||  ._________.  | |
         \ ._____.  |    ___________________   ||  | _______ |  | |
    /-+  | |     |  |    |________ ________|   ||  | |     | |  | |
    | |  \ |     | /             | |           ||  | |_____| |  | |
   /  /   | \   _| |             | |           ||  |  _____  |  | |
   | |    \  \ /  /              | |           ||  | |     | |  | |
  /  /     \  v  /               | |           ||  | |_____| |  | |
  | /      _>   <                | |           ||  |_________|  | |
 /  |  ___/  /\  \____   ._______| |________.  ||               | |
 |-/  /_____/  \______\  |__________________|  |/               \_|

    _   _         ____  _     _      ____                       _ _ _
   | \ | | ___   |  _ \(_)___| | __ / ___| _ __   __ _  ___ ___| | | |
   |  \| |/ _ \  | | | | / __| |/ / \___ \| ._ \ / _\ |/ __/ _ \ | | |
   | |\  | (_) | | |_| | \__ \   <   ___) | |_) | (_| | (_|  __/_|_|_|
   |_| \_|\___/  |____/|_|___/_|\_\ |____/| .__/ \__,_|\___\___(_|_|_)
                                          |_|
  "
  printf "\e[0m"
  exit 1
}

# Initialize system TTY.
init_tty() {
  # Preventing ttyN (developer shell console) to go blank after some idle time
  local tty=""
  for tty in /dev/tty[2-4]; do
    (setterm -cursor on -blank 0 -powerdown 0 -powersave off
     >"${tty}") 2>/dev/null || true
  done
}

# Initialize kernel modules and system daemons.
init_modules() {
  # We disable powerd in factory image, but this folder is needed for some
  # commands like power_supply_info to work.
  mkdir -p /var/lib/power_manager

  # Preload modules here
  modprobe i2c-dev 2>/dev/null || true
}

# Initialize firewall settings.
init_firewall() {
  # Open ports in the firewall so that the presenter can reach us
  # Note we want these ports to be expanded as a list, and so are unquoted
  local port=
  for port in $GOOFY_LINK_PORTS $GOOFY_UI_PORT; do
    /sbin/iptables -A INPUT -p tcp --dport ${port} -j ACCEPT
  done
}

# http://crbug.com/410233: If TPM is owned, UI may get freak.
check_tpm() {
  if [ "$(crossystem mainfw_type 2>/dev/null)" = "nonchrome" ] ||
     [ "$(cat /sys/class/misc/tpm0/device/owned 2>/dev/null)" != "1" ]; then
    return
  fi
  # If TPM is owned, we have to reboot otherwise UI may get freak.
  # Alert user and try to clear TPM.
  stop -n ui >/dev/null 2>&1 &
  echo "
        Sorry, you must clear TPM owner before running factory UI.
        We are going to do that for you (and then reboot) in 10 seconds.

        If you want to abort, do Ctrl-Alt-F2, login, and run

          stop factory
       "
  show_interactive_console
  for i in $(seq 10 -1 0); do
    echo " > Clear & reboot in ${i} seconds..."
    sleep 1
  done

  crossystem clear_tpm_owner_request=1
  echo "Restarting system..."
  reboot
  # Wait forever.
  sleep 1d
}

start_factory() {
  init_output

  echo "
    Starting factory program...

    If you don't see factory window after more than one minute,
    try to switch to VT2 (Ctrl-Alt-F2), log in, and check the messages by:
      tail $SESSION_LOG_FILE $FACTORY_LOG_FILE

    If it keeps failing, try to reset by:
      factory_restart -a
  "

  load_setup

  init_modules
  init_tty
  init_firewall

  check_tpm
  check_disk_usage

  if [ -z "$(status ui | grep start)" ]; then
    echo "Request to start UI..."
    start -n ui &
  fi

  export DISPLAY=":0"
  export XAUTHORITY="/home/chronos/.Xauthority"

  # Rules to start Goofy. Not this has to sync with init/startup.
  local tag_device="${RUN_GOOFY_DEVICE_TAG_FILE}"
  local tag_presenter="${RUN_GOOFY_PRESENTER_TAG_FILE}"
  if [ -f "${tag_presenter}" -a ! -f "${tag_device}" ]; then
    # Presenter-only mode.
    # Note presenter output is only kept in SESSION_LOG_FILE.
    echo "Starting Goofy Presenter... ($PRESENTER_ARGS)"
    "$FACTORY/bin/goofy_presenter" $PRESENTER_ARGS &
  else
    if [ ! -f "${tag_presenter}" -a -f "${tag_device}" ]; then
      # Device-only mode.
      true
    else
      # Stand-alone mode.
      GOOFY_ARGS="${GOOFY_ARGS} --standalone"
    fi
    echo "Starting Goofy Device... ($GOOFY_ARGS)"
    echo "
    --- $(date +'%Y%m%d %H:%M:%S') Starting new Goofy session ($GOOFY_ARGS) ---
         " >>"$FACTORY_LOG_FILE"
    "$FACTORY/bin/goofy" $GOOFY_ARGS >>"$FACTORY_LOG_FILE" 2>&1 &
  fi

  wait
}

stop_factory() {
  # Try to kill X, and any other Python scripts, five times.
  echo -n "Stopping factory."
  for i in $(seq 5); do
    pkill 'python' || break
    sleep 1
    echo -n "."
  done

  echo "

    Factory tests terminated. To check error messages, try
      tail ${SESSION_LOG_FILE} ${FACTORY_LOG_FILE}

    To restart, press Ctrl-Alt-F2, log in, and type:
      factory_restart

    If restarting does not work, try to reset by:
      factory_restart -a
    "
}

main() {
  case "$1" in
    "start" )
      start_factory "$@"
      ;;

    "stop" )
      stop_factory "$@"
      ;;

    * )
      echo "Usage: $0 [start|stop]" >&2
      exit 1
      ;;
  esac
}

main "$@"
