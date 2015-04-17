#!/bin/sh
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Configure DHCP server.
#

SCRIPT_NAME="$(readlink -f "$0")"
DHCPD_IFACE=""
DHCPD_CONF="${SCRIPT_NAME%.*}.conf"
DHCPD_VAR="/var/lib/dhcp"
LEASE_FILE="${DHCPD_VAR}/dhcpd.leases"

echo "looking for built-in ethernet..."
while true; do
  for eth in /sys/class/net/eth?; do
    if [ "$(readlink -f "${eth}/device/subsystem")" = "/sys/bus/pci" ]; then
      DHCPD_IFACE="$(basename "$eth")"
    fi
  done
  if [ -z "${DHCPD_IFACE}" ]; then
    printf "." >&2
    sleep 1
  else
    echo ""
    break
  fi
done
echo "using ${DHCPD_IFACE} for subnet..."
# Tell shill stop watching built-in ethernet.
/usr/local/lib/flimflam/test/disable-device "${DHCPD_IFACE}"
ifconfig "${DHCPD_IFACE}" 192.168.231.1 netmask 255.255.255.0 up

echo "preparing lease and pid files for dhcpd"
mkdir -m 0755 -p "${DHCPD_VAR}"
chmod -R u+rwX,g+rX,o+rX "${DHCPD_VAR}"
chown -R dhcp:dhcp "${DHCPD_VAR}"
if [ ! -f "${LEASE_FILE}" ] ; then
  touch "${LEASE_FILE}"
  chown dhcp:dhcp "${LEASE_FILE}"
fi

echo "checking and disabling firewall..."
IPTABLES_RULE="-i ${DHCPD_IFACE} -p udp --dport 67:68 -j ACCEPT"
# Note we have to insert as first rule otherwise UDP data may be filtered by
# NFQUEUE rules.
iptables -C INPUT ${IPTABLES_RULE} 2>/dev/null ||
  iptables -I INPUT 1 ${IPTABLES_RULE}

echo "Starting DHCP service against ${DHCPD_IFACE}"
exec /usr/local/sbin/dnsmasq -k -d \
  -C "${DHCPD_CONF}" -l "${LEASE_FILE}" -i "${DHCPD_IFACE}"
