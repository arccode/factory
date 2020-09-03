#!/bin/sh
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Customize Chrome startup settings.

conf_dir="$(dirname $0)"
conf_file="${conf_dir}/chrome_dev.conf"
model="$(cros_config / name || true)"
board_conf_file="${conf_dir}/chrome_dev_board.conf"
model_conf_file="${conf_dir}/chrome_dev_${model}.conf"

# If model or board conf file from board overlay exists, use it
if [ -f "${model_conf_file}" ]; then
  conf_file="${model_conf_file}"
elif [ -f "${board_conf_file}" ]; then
  conf_file="${board_conf_file}"
fi

mount --bind "${conf_file}" /etc/chrome_dev.conf

# For factory environment, we don't need to preserve Chrome session data.
# /home/chronos may have been mounted by stateful partition and encstateful.
umount -R /home/chronos || true
mount -t tmpfs none /home/chronos

# Chrome uses /var/tmp to create some sqlite database files and would raise
# profile error if writing to /var/tmp failed (for example, encstateful full).
# To speed up and ensure Chrome can run without problems, mount /var/tmp as
# tmpfs.
mount -t tmpfs none /var/tmp

# Enable all debug-friendly features, by information from following page:
# http://www.chromium.org/chromium-os/how-tos-and-troubleshooting/debugging-tips
# On ToT, having disable_chrome_restart before job 'ui' starts would block
# Chrome to execute. Please manually do the line below after Chrome starts.
# touch /run/disable_chrome_restart
# Chromium dumps may fill up system space in early protos so we want to do it
# manually. Uncomment the 2 lines below if you need to get dumps.
# touch /root/.leave_core
# touch /mnt/stateful_partition/etc/collect_chrome_crashes
