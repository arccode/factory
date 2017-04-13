#!/bin/sh
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# A script to generate a "trusted" device identifier.

# Use disk storage name and serial number to build device id.
id_storage() {
  local device="$1"

  if [ -z "${device}" ]; then
    device="$(rootdev -s -d)"
  fi

  # Normally this is done by /etc/init/udev-trigger.conf.
  # Since the script would be run at system startup, before the udev-trigger is
  # run, we need to do this by ourselves.
  udevadm trigger --subsystem-match block
  udevadm settle

  udevadm info --query symlink "${device}" | md5sum | cut -d ' ' -f 1
}

# Collect all ethernet type network interfaces and compute a hash.
id_ethernet() {
  ip addr | grep link/ether | sort | md5sum | sed 's/ .*//'
}

main() {
  set -e
  id_storage "$@"
}
main "$@"
