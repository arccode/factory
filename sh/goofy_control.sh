#!/bin/bash
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

set -e
FACTORY="$(dirname "$(dirname "$(readlink -f "$0")")")"
FACTORY_LOG_FILE=/var/factory/log/factory.log

BOARD_SETUP=("$FACTORY/board/board_setup_factory.sh"
             "$FACTORY/custom/board_setup_factory.sh")

# Default args for Goofy.
GOOFY_ARGS=""

# If this exits, then start factory with automation
AUTOMATION_FILE="/var/factory/state/factory.automation"

# Default implementation for factory_setup (no-op).  May be overriden
# by board_setup_factory.sh.
factory_setup() {
    true
}

# Show splash screen
boot_splash() {
    SPLASH_IMAGES_DIR="/usr/share/chromeos-assets/images_200_percent"
    SPLASH_IMAGES="$SPLASH_IMAGES_DIR"/boot_splash_frame*.png
    ply-image --clear 0xfefefe --frame-interval 25 $SPLASH_IMAGES --offset=0,-40
    sleep 0.2
    ply-image "/usr/local/factory/misc/boot_splash.png" --offset=0,+80
    sleep 0.1
}

load_setup() {
  # Load board-specific parameters, if any.
  for f in "${BOARD_SETUP[@]}"; do
    if [ -s $f ]; then
      echo "Loading board-specific parameters $f..." 1>&2
      . $f
      break
    fi
  done

  if [ -f $AUTOMATION_FILE ]; then
    echo "Automation is enabled" 1>&2
    GOOFY_ARGS="$GOOFY_ARGS --automation"
  fi

  factory_setup
}

check_disk_usage() {
  # Show error in red
  echo -e "\033[1;31m"
  "$FACTORY/bin/disk_space" 2>&1 1>/dev/null || exit 1
  echo -e "\033[0m"
}

start_factory() {
  # This should already exist, but just in case...
  mkdir -p "$(dirname "$FACTORY_LOG_FILE")"
  ln -sf "$FACTORY_LOG_FILE" /var/log

  load_setup
  echo "
    Starting factory program...

    If you don't see factory window after more than one minute,
    try to switch to VT2 (Ctrl-Alt-F2), log in, and check the messages by:
      tail $FACTORY_LOG_FILE

    If it keeps failing, try to reset by:
      factory_restart -a
  "

  # We disable powerd in factory image, but this folder is needed for some
  # commands like power_supply_info to work.
  mkdir -p /var/lib/power_manager

  # Preload modules here
  modprobe i2c-dev 2>/dev/null || true
  check_disk_usage
  boot_splash

  cd "$FACTORY"/../autotest
  eval "$("$FACTORY/sh/startx.sh" 2>/var/log/startx.err)"
  "$FACTORY/bin/goofy" $GOOFY_ARGS >>"$FACTORY_LOG_FILE" 2>&1
}

stop_factory() {
  load_setup
  # Try to kill X, and any other Python scripts, five times.
  echo -n "Stopping factory."
  for i in $(seq 5); do
    pkill 'X|python' || break
    sleep 1
    echo -n "."
  done

  echo "

    Factory tests terminated. To check error messages, try
      tail $FACTORY_LOG_FILE

    To restart, press Ctrl-Alt-F2, log in, and type:
      factory_restart

    If restarting does not work, try to reset by:
      factory_restart -a
    "
}

case "$1" in
  "start" )
    start_factory "$@"
    ;;

  "stop" )
    stop_factory "$@"
    ;;

  * )
    echo "Usage: $0 [start|stop]"
    exit 1
    ;;
esac
