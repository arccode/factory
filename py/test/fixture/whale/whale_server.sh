#!/bin/sh
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Configure DHCP and TFTP servers.
#

SCRIPT_NAME="$(readlink -f "$0")"
SCRIPT_DIR="$(dirname $SCRIPT_NAME)"
DHCPD_IFACE=""
DHCPD_CONF="${SCRIPT_NAME%.*}.conf"
DHCPD_VAR="/var/lib/dhcp"
LEASE_FILE="${DHCPD_VAR}/dhcpd.leases"
NUC_IP="192.168.234.1"
TFTP_ROOT="/usr/local/factory/tftp_boot"

echo "set up TFTP..."
mkdir -m 0755 -p $TFTP_ROOT

echo "looking for built-in Ethernet network..."
DHCPD_IFACE="$(${SCRIPT_DIR}/../get_builtin_eth.sh)"
echo "looking for dongle Ethernet network..."
DONGLE_IFACE="$(${SCRIPT_DIR}/../get_dongle_eth.sh)"

echo "using ${DHCPD_IFACE} for subnet..."
# Tell shill stop watching built-in ethernet.
/usr/local/lib/flimflam/test/disable-device "${DHCPD_IFACE}"
ifconfig "${DHCPD_IFACE}" ${NUC_IP} netmask 255.255.255.0 up

echo "preparing lease and pid files for dhcpd"
mkdir -m 0755 -p "${DHCPD_VAR}"
chmod -R u+rwX,g+rX,o+rX "${DHCPD_VAR}"
chown -R dhcp:dhcp "${DHCPD_VAR}"
# Always clean up DHCPD lease when NUC boots up. It's for the case:
# only one IP has been assigned, change another ethernet dongle, and
# reboot to get an IP for the new dongle.
echo "" > ${LEASE_FILE}
chown dhcp:dhcp ${LEASE_FILE}


echo "checking and disabling firewall..."
IPTABLES_RULE="-i ${DHCPD_IFACE} -p udp --dport 67:69 -j ACCEPT"
# Note we have to insert as first rule otherwise UDP data may be filtered by
# NFQUEUE rules.
iptables -C INPUT ${IPTABLES_RULE} 2>/dev/null ||
  iptables -I INPUT 1 ${IPTABLES_RULE}

echo "set up NAT(${DONGLE_IFACE})..."
echo 1 > /proc/sys/net/ipv4/ip_forward
iptables -P FORWARD ACCEPT
iptables -t nat -A POSTROUTING -o ${DONGLE_IFACE} -j MASQUERADE

echo "Starting DHCP service against ${DHCPD_IFACE}"
exec /usr/local/sbin/dnsmasq -k -d \
  -C "${DHCPD_CONF}" -l "${LEASE_FILE}" -i "${DHCPD_IFACE}"

