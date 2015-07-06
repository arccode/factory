#!/bin/sh
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Looks up Ethernet dongle and prints the node name if found.

ETHERNET_IFACE=""

while true; do
  for eth in /sys/class/net/eth?; do
    if [ "$(readlink -f "${eth}/device/subsystem")" = "/sys/bus/usb" ]; then
      ETHERNET_IFACE="$(basename "$eth")"
    fi
  done

  if [ -z "${ETHERNET_IFACE}" ]; then
    printf "." >&2
    sleep 1
  else
    echo $ETHERNET_IFACE
    break
  fi
done

