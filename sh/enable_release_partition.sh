#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script performs following tasks to switch active partition:
# - enable release partition and disable factory release partition
# - (legacy firmware) perform "postinst" to configure legacy boot loaders
# - rollback if anything goes wrong

. "$(dirname "$(readlink -f $0)")"/common.sh || exit 1
set -e

# Kernel activation parameters
ENABLED_KERNEL_PRIORITY="3"

# Variables for cleaning up
NEED_ROLLBACK=""

# usage: enable_kernel partition_no
enable_kernel() {
  alert "Enabling kernel on $CGPT_DEVICE #$1 ..."
  cgpt add -i "$1" -P "$ENABLED_KERNEL_PRIORITY" -S 1 -T 0 "$CGPT_DEVICE"
  cgpt prioritize -i "$1" -P "$ENABLED_KERNEL_PRIORITY" "$CGPT_DEVICE"
}

# usage: disable_kernel partition_no
disable_kernel() {
  alert "Disabling kernel on $CGPT_DEVICE #$1 ..."
  cgpt add -i "$1" -P 0 -S 0 -T 0 "$CGPT_DEVICE"
}

rollback_changes() {
  # don't stop, even if we encounter any issues
  local failure_msg="WARNING: Failed to rollback some changes..."
  alert "WARNING: Rolling back changes."
  crossystem disable_dev_request=0 || alert "$failure_msg"
  if [ -n "$CGPT_CONFIG" ]; then
    cgpt_restore_status "$CGPT_DEVICE" "$CGPT_CONFIG" || alert "$failure_msg"
  fi
}

cleanup() {
  if [ -n "$NEED_ROLLBACK" ]; then
    rollback_changes
  fi
}

main() {
  if [ "$#" != "1" ]; then
    alert "Usage: $0 release_rootfs"
    exit 1
  fi

  local release_rootfs="$1"
  local factory_rootfs="$(echo "$release_rootfs" | tr '35' '53')"
  [ "$release_rootfs" != "$factory_rootfs" ] ||
    die "Unknown type of device: $release_rootfs"
  cgpt_init "$(device_remove_partno "$release_rootfs")" ||
    die "Failed to initialize device: $release_rootfs"

  local release_partno="$(echo "$release_rootfs" | sed -r 's/.*([0-9])$/\1/')"
  local factory_partno="$(echo "$factory_rootfs" | sed -r 's/.*([0-9])$/\1/')"
  [ -n "$release_partno" -a -n "$factory_partno" ] ||
    die "Failed to identify release/factory partition numbers: $release_rootfs"

  NEED_ROLLBACK="YES"
  if chromeos_is_legacy_firmware; then
    # When booting with legacy firmware, we need to update the legacy boot
    # loaders to activate new kernel; on a real ChromeOS firmware, only CGPT
    # header is used, and postinst is already performed in verify_rootfs.
    alert "Running on legacy system, invoke postinst."
    chromeos_invoke_postinst "$release_rootfs"
  fi
  disable_kernel "$(( factory_partno - 1 ))"
  enable_kernel "$(( release_partno - 1 ))"
  crossystem disable_dev_request=1
  alert "Syncing disks..."
  sync
  sleep 3  # For sync to take place.
  NEED_ROLLBACK=""
  alert "Enable release partition: Complete."
}

trap cleanup EXIT
main "$@"
