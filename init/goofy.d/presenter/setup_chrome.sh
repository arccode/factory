#!/bin/sh
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Customize Chrome startup settings.
mount --bind "$(dirname $0)/chrome_dev.conf" /etc/chrome_dev.conf

# For factory environment, we don't need to preserve Chrome session data.
mount -t tmpfs none /home/chronos

# Enable all debug-friendly features, by information from following page:
# http://www.chromium.org/chromium-os/how-tos-and-troubleshooting/debugging-tips
touch /var/run/disable_chrome_restart
# Chromium dumps may fill up system space in early protos so we want to do it
# manually. Uncomment the line below if you need to get dumps.
# touch /mnt/stateful_partition/etc/enable_chromium_coredumps
