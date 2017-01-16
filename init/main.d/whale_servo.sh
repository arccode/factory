#!/bin/sh
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

MYDIR="$(dirname "$(readlink -f "$0")")"
FACTORY_BASE="/usr/local/factory"

CONFIG_FILE="${MYDIR}/../run_whale_servo"

SHILL_BIN="/usr/bin/shill"
DISABLED_BIN="${FACTORY_BASE}/sh/disabled.sh"

# Based on Whale network topology: http://goo.gl/rrvT8C
IP_ADDRESS="192.168.234.2"

WHALE_SERVO_BIN="${FACTORY_BASE}/py/test/fixture/whale/host/whale_servo"
DOLPHIN_SERVER_BIN="${FACTORY_BASE}/py/test/fixture/whale/host/dolphin_server"

start_servod() {
  . ${CONFIG_FILE}
  if [ -n "${BOARD}" ]; then
    start servod "BOARD=${BOARD}"
  else
    echo "Unable to resolve BOARD name"
  fi
}

start_network() {
  # Disable shill
  mount --bind ${DISABLED_BIN} ${SHILL_BIN}
  ifconfig lo 127.0.0.1 netmask 255.0.0.0 up
  ifconfig eth0 ${IP_ADDRESS} netmask 255.255.255.0 up
}

main() {
  start_servod
  start_network
  # TODO(deanliao): make interrupt_handler as a service.
  ${DOLPHIN_SERVER_BIN} ${BOARD} &
  ${WHALE_SERVO_BIN} &
  wait
}

main
