#!/bin/sh
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script verifies if a chromeos rootfs is valid for activation, by running
# the chromeos-postinst script.

. "$(dirname "$0")/common.sh" || exit 1
set -e
NEED_ROLLBACK=""

rollback_changes() {
  # don't stop, even if we encounter any issues
  local failure_msg="WARNING: Failed to rollback some changes..."
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

  # No matter what, revert cgpt changes.
  NEED_ROLLBACK="YES"

  # TODO(hungte) Using chromeos_invoke_postinst here is leaving a window where
  # unexpected reboot or test exit may cause the system to boot into the release
  # image. Currently "cgpt" is very close to the last step of postinst so it may
  # be OK, but we should seek for better method for this, for example adding a
  # "--nochange_boot_partition" to chromeos-postinst.
  chromeos_invoke_postinst "$release_rootfs"
  if chromeos_is_legacy_firmware; then
    # Reverting legacy boot loaders -- only required if current system is using
    # a legacy firmware. Setting legacy boot partition to "1" would prevent
    # unexpected reboots during next chromeos_invoke_postinst to bring up
    # release OS image.
    cgpt boot -i "1" "$CGPT_DEVICE"
    chromeos_invoke_postinst "$factory_rootfs"
  fi
}

trap cleanup EXIT
main "$@"
