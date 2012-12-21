#!/bin/bash

# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

XAUTH=/usr/bin/xauth
XAUTH_FILE=/home/chronos/.Xauthority
SERVER_READY=
DISPLAY=":0"

FACTORY="$(dirname "$(dirname "$(readlink -f "$0")")")"
BOARD_SETUP=("$FACTORY/board/board_setup_x.sh"
             "$FACTORY/custom/board_setup_x.sh")

# Default X server parameters
X_ARG="-r -s 0 -p 0 -dpms -nolisten tcp vt01 -auth ${XAUTH_FILE}"

board_pre_setup() {
  true
}

board_post_setup() {
  true
}

setup_xauth() {
  MCOOKIE=$(head -c 8 /dev/urandom | md5sum | cut -d' ' -f1)
  ${XAUTH} -q -f ${XAUTH_FILE} add ${DISPLAY} . ${MCOOKIE}
}

setup_cursor() {
  # The following logic is copied from /sbin/xstart.sh to initialize the
  # touchpad device adequately.
  if [ -d /home/chronos -a ! -f /home/chronos/.syntp_enable ] ; then
    # serio_rawN devices come from the udev rules for the Synaptics binary
    # driver throwing the PS/2 interface into raw mode.  If we find any
    # that are TP devices, put them back into normal mode to use the default
    # driver instead.
    for P in /sys/class/misc/serio_raw*
    do
      # Note: It's OK if globbing fails, since the next line will drop us out
      udevadm info -q env -p $P | grep -q ID_INPUT_TOUCHPAD=1 || continue
      # Rescan everything; things that don't have another driver will just
      # restart in serio_rawN mode again, since they won't be looking for
      # the disable in their udev rules.
      SERIAL_DEVICE=/sys$(dirname $(dirname $(udevadm info -q path -p $P)))
      echo -n "rescan" > ${SERIAL_DEVICE}/drvctl
    done
  else
    udevadm trigger
    udevadm settle
  fi
}

user1_handler () {
  echo "X server ready..." 1>&2
  SERVER_READY=y
}

start_x_server() {
  trap user1_handler USR1
  /bin/sh -c "
    trap '' USR1 TTOU TTIN
    exec /usr/bin/X $X_ARG 2>/var/log/factory.X.log" &

  while [ -z ${SERVER_READY} ]; do
    sleep .1
  done
}

# Load board-specific parameters, and override any startup procedures.
for f in "${BOARD_SETUP[@]}"; do
  if [ -s $f ]; then
    echo "Loading board-specific X parameters $f..." 1>&2
    . $f
    break
  fi
done

board_pre_setup

setup_xauth
setup_cursor

start_x_server

export DISPLAY=${DISPLAY}
export XAUTHORITY=${XAUTH_FILE}

board_post_setup

/sbin/initctl emit factory-ui-started
cat /proc/uptime > /tmp/uptime-x-started

echo "export DISPLAY=${DISPLAY}"
echo "export XAUTHORITY=${XAUTH_FILE}"
