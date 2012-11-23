#!/bin/sh

# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Script to mount a partition chromiumos image.
# Rootfs with ext2 RO-bit turned on will be mounted with read-only flags,
# and other kinds of file systems will be mounted in read-writable mode.

. "$(dirname "$(readlink -f "$0")")/factory_common.sh" || exit 1

main() {
  set -e

  # Check parameter and environment.
  if [ "$#" != 3 ]; then
    die "Usage: $0 cros_image_file partition_index mount_point

    Ex: $0 chromiumos_image.bin 3 /media"
  fi
  if ! image_has_part_tools; then
    die "Missing partition tools. Please install cgpt/parted, or run in chroot."
  fi

  local image_file="$1"
  local partition_index="$2"
  local mount_point="$3"

  # Basic checking
  [ -f "$image_file" ] || die "Cannot find image file: $image_file"
  [ -d "$mount_point" ] || die "Invalid mount point: $mount_point"

  # Check image format.
  local part_offset="$(
    image_part_offset "$image_file" "$partition_index" 2>/dev/null)" || true
  if [ -z "$part_offset" ] || [ "$part_offset" -le "0" ]; then
    die "Invalid image file $image_file for partition #$partition_index."
  fi

  # Try to mount with default options, or RO+ext2 if that failed.
  if ! image_mount_partition "$image_file" "$partition_index" "$mount_point" \
                             "rw" "" 2>/dev/null; then
    # "-t ext2" must be explicitly specified otherwise ext4+ file system module
    # may change some meta data inside superblock, even in read-only mode.
    image_mount_partition "$image_file" "$partition_index" "$mount_point" \
                          "ro" "-t ext2" ||
        die "Failed to mount $image_file partition #$partition_index."
    warn "WARNING: PARTITION #$partition_index IS READ-ONLY!"
  fi
  info "Mounted $image_file#$partition_index at $mount_point."
}

main "$@"
