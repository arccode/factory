#!/bin/sh
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script prints the CHROMEOS_RELEASE_BOARD variable from /etc/lsb-release
# file of a root file system.

. "$(dirname "$0")/common.sh" || exit 1
set -e

chromeos_get_release_board() {
  local rootdev="$1"
  local mount_point="$(mktemp -d --tmpdir)"

  # Always mount fs as ext2 to prevent unexpected writes
  mount -t ext2 -o ro "$rootdev" "$mount_point" || {
    alert "Failed to mount partition $rootdev."
    rmdir "$mount_point" || true
    return 1
  }
  cat "$mount_point"/etc/lsb-release |
    grep -E '^[\s]*CHROMEOS_RELEASE_BOARD' |
    sed 's/[^=]*=//g;'

  umount -f "$mount_point" ||
    alert "WARNING: Failed to unmount partition $rootdev"
  rmdir "$mount_point" || true
}

if [ "$#" != "1" ]; then
  die "Usage: $0 rootfs_dev"
fi
chromeos_get_release_board "$@"
