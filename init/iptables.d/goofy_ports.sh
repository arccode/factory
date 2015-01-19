#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Ports used by goofy
GOOFY_UI_PORT="4012"
GOOFY_LINK_PORTS="4020 4021 4022 4023"

for port in $GOOFY_LINK_PORTS $GOOFY_UI_PORT; do
  /sbin/iptables -A INPUT -p tcp --dport ${port} -j ACCEPT
done
