#!/bin/sh
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Look up built-in Ethernet interface.
# If found, prints the node name.

ETHERNET_IFACE=""

while true; do
  for eth in /sys/class/net/eth?; do
    if [ "$(readlink -f "${eth}/device/subsystem")" = "/sys/bus/pci" ]; then
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

