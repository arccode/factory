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
# On ToT, having disable_chrome_restart before job 'ui' starts would block
# Chrome to execute. Please manually do the line below after Chrome starts.
# touch /var/run/disable_chrome_restart
# Chromium dumps may fill up system space in early protos so we want to do it
# manually. Uncomment the line below if you need to get dumps.
# touch /mnt/stateful_partition/etc/enable_chromium_coredumps
