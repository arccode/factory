#!/bin/bash
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FACTORY_BASE="/usr/local/factory"
DPSERVER_LEFT_LOG="/var/log/whale_dp_server_left.log"
DPSERVER_RIGHT_LOG="/var/log/whale_dp_server_right.log"

serve_whale_host() {

  "${FACTORY_BASE}/bin/whale_server" 2>&1 &

  # Open DP server port (9997-9998).
  local rule1="INPUT -p tcp --dport 9997 -j ACCEPT"
  local rule2="INPUT -p tcp --dport 9998 -j ACCEPT"
  iptables -C "${rule1}" 2>/dev/null || iptables -A "${rule1}"
  iptables -C "${rule2}" 2>/dev/null || iptables -A "${rule2}"

  # Start DP servers.
  "${FACTORY_BASE}/bin/dolphin_uno_server" --hdmi --checkhdmi --port=9997 \
      --debug --uvc_port=[23]-4 --uvc_device_name=Left_Raiden \
      >"$DPSERVER_LEFT_LOG" 2>&1 &
  "${FACTORY_BASE}/bin/dolphin_uno_server" --hdmi --checkhdmi --port=9998 \
      --debug --uvc_port=[23]-3 --uvc_device_name=Right_Raiden \
      >"$DPSERVER_RIGHT_LOG" 2>&1 &
}

serve_whale_host
