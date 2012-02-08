#!/bin/sh

# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

XAUTH=/usr/bin/xauth
XAUTH_FILE=/home/chronos/.Xauthority
SERVER_READY=
DISPLAY=":0"

SUITE_FACTORY="$(dirname "$0")"/../../site_tests/suite_Factory
BOARD_CONFIG="$(readlink -f "$SUITE_FACTORY")/board_config_x.sh"

user1_handler () {
  echo "X server ready..." 1>&2
  SERVER_READY=y
}

trap user1_handler USR1
MCOOKIE=$(head -c 8 /dev/urandom | openssl md5)
${XAUTH} -q -f ${XAUTH_FILE} add ${DISPLAY} . ${MCOOKIE}

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

/bin/sh -c "\
trap '' USR1 TTOU TTIN
exec /usr/bin/X -nolisten tcp vt01 -auth ${XAUTH_FILE} \
-r -s 0 -p 0 -dpms 2> /var/log/factory.X.log" &

while [ -z ${SERVER_READY} ]; do
  sleep .1
done

export DISPLAY=${DISPLAY}
export XAUTHORITY=${XAUTH_FILE}

if [ -x $BOARD_CONFIG ]; then
  $BOARD_CONFIG
fi

/sbin/initctl emit factory-ui-started
cat /proc/uptime > /tmp/uptime-x-started

echo "export DISPLAY=${DISPLAY}"
echo "export XAUTHORITY=${XAUTH_FILE}"
