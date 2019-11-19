#!/bin/bash
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

set -e

# Most projects seem to prefer having unlimited core dump.
# To disable this, override factory_setup in `board_setup_factory.sh`.
ulimit -c unlimited || true

. /usr/local/factory/sh/common.sh

FACTORY="$(dirname "$(dirname "$(readlink -f "$0")")")"
FACTORY_LOG_FILE=/var/factory/log/factory.log
SESSION_LOG_FILE=/var/log/factory-session.log
INTERACTIVE_CONSOLES=""
LOG_PROCESSES=""

BOARD_SETUP="${FACTORY}/board/board_setup_factory.sh"

# Put '/usr/local/factory/bin' at the head of PATH so that Goofy doesn't need to
# specify full path name when running factory binaries.
export PATH="/usr/local/factory/bin:${PATH}"

# Default args for Goofy.
GOOFY_ARGS=""

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
  mkdir -p "$(dirname "${FACTORY_LOG_FILE}")"
  touch "${FACTORY_LOG_FILE}"
  # To help reading archived logs (not on DUT), we assume the FACTORY_LOG_FILE
  # starts with /var and try to create the symlink as relative path.
  ln -sf "../${FACTORY_LOG_FILE#/var/}" /var/log

  # Provide the latest factory log on TTY3 if available.
  local tty_log=/dev/tty3
  if [ -c "${tty_log}" ]; then
    setsid sh -c \
      "script -afqc 'while true; do less -W +F ${FACTORY_LOG_FILE}; done' \
       /dev/null <${tty_log} >${tty_log}" &
  fi
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
    if chvt "${vt_index}"; then
      return
    fi
  done
}

# Load board-specific parameters, if any.
load_setup() {
  if [ -s "${BOARD_SETUP}" ]; then
    echo "Loading board-specific parameters ${BOARD_SETUP}..."
    . "${BOARD_SETUP}"
  fi

  factory_setup
}

# Checks disk usage and abort if running out of disk space.
check_disk_usage() {
  # /tmp should be mounted as tmpfs so it should be always available.
  local out_dir="$(mktemp -d)"

  local df_output="${out_dir}/df"
  if "${FACTORY}/bin/disk_space" >"${df_output}"; then
    cat "${df_output}"
    rm -rf "${out_dir}"
    return
  fi

  # Try to setup a HTTP server for Chrome to display.
  local out_file="${out_dir}/index.html"
  local template_file="${FACTORY}/misc/no_space.html"
  mkdir -p "${out_dir}"
  sed -i -e "s/ \[/\\n [/g" "${df_output}"
  find /var -size +100M -print0 | xargs -0 du -sh | sort -hr >>"${df_output}"
  toybox sed -e "/DISK_USAGE_INFO/r ${df_output}" "${template_file}" \
    >"${out_file}"
  # This should be the port specified by chrome_dev.conf.
  exec busybox httpd -f -p 4012 -h "${out_dir}"
}

# Initialize system TTY.
init_tty() {
  # Preventing ttyN (developer shell console) to go blank after some idle time
  local tty=""
  for tty in /dev/tty[2-4]; do
    if [ -c "${tty}" ]; then
      (setterm -cursor on -blank 0 -powerdown 0 -powersave off
        >"${tty}") 2>/dev/null || true
    fi
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

# Initialize network settings.
init_network() {
  # Make sure local loopback device is activated
  ifconfig lo up
}

start_system_services() {
  # 'system-services' is started by ui.conf -> session_manager -> Chrome ->
  # dbus.EmitLoginPromptVisible -> boot-complete -> system-services.
  # Since we start Chrome without login manager, the dbus event must be sent
  # explicitly. This was done in Goofy by waiting for connection, but we've
  # found that on recent systems Chrome may need system services to be ready
  # before it can start entering main page, so we want to do this as early as
  # possible, immediately after session manager is ready. Unfortunately there is
  # no way to find that except directly looking at dbus contents.
  echo "[LoginPromptVisible] Start trying to emit dbus event..."
  local retries=30
  while ! dbus-send --system --dest=org.chromium.SessionManager \
            --print-reply /org/chromium/SessionManager \
            org.chromium.SessionManagerInterface.EmitLoginPromptVisible; do
    if [ "${retries}" -lt 1 ]; then
      echo "[LoginPromptVisible] Timed out, trying to run in fail-safe mode..."
      initctl emit login-prompt-visible || true
      start -n system-services || true
      return
    fi
    retries=$((retries - 1))
    sleep 1
  done
  echo "[LoginPromptVisible] Event sent, system-services should start later."
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
  init_network

  check_disk_usage

  if status ui | grep -vq start; then
    echo "Request to start UI..."
    start -n ui &
  fi
  start_system_services &

  # It's hard to display any messages under Frecon, and Chrome usually starts
  # even when disk is full, so we want to check disk usage after UI started.
  check_disk_usage

  export DISPLAY=":0"
  export XAUTHORITY="/home/chronos/.Xauthority"

  echo "Starting Goofy... ($GOOFY_ARGS)"
  echo "
  --- $(date +'%Y%m%d %H:%M:%S') Starting new Goofy session ($GOOFY_ARGS) ---
  Device ID: $(cat /var/factory/.device_id) " >>"$FACTORY_LOG_FILE"
  # shellcheck disable=SC2086
  "$FACTORY/bin/goofy" $GOOFY_ARGS >>"$FACTORY_LOG_FILE" 2>&1 &

  wait
}

stop_factory() {
  # Try to kill X, and any other Python scripts, five times.
  echo -n "Stopping factory."
  local i
  # shellcheck disable=SC2034
  for i in $(seq 5); do
    pkill 'python2' || break
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
