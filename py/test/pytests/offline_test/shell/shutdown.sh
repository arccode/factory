#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

task_{%id%} () {
  if [ ! -e "${DATA_DIR}/rebooted" ]; then
    touch "${DATA_DIR}/should_reboot"
    touch "${DATA_DIR}/rebooted"
    sync
    sleep 3  # for spinning disks to flush

    reboot

    sleep 60

    die Failed to shutdown
  else
    rm -f "${DATA_DIR}/rebooted"
    return 0
  fi
}
