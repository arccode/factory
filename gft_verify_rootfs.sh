#!/bin/sh
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Derived from chromeos-setimage.
#
# A script to verify rootfs disk image hash.

TMPDIR=""
TMPFILE=""
set -e

alert() {
  echo "$*" 1>&2
}

clean_up() {
  umount -f "$TMPDIR" 2>/dev/null || true
  rm -rf "$TMPDIR" "$TMPFILE"
}

# Usage: $0 kernel_image rootfs_image
main() {
  if [ "$#" != "2" ]; then
    alert "ERROR: Usage: $0 kernel_device rootfs_device"
    exit 1
  fi

  local kernel_image="$1"
  local rootfs_image="$2"

  TMPDIR="$(mktemp -d)"
  TMPFILE="$(mktemp)"
  trap clean_up EXIT

  # Verity processing logic here is based on chromeos-setimage.
  # kernel_config sample:
  #  dm="vroot none ro,0 1740800 verity %U+1 %U+1 1740800 0 sha1 2ad712bb6..."
  kernel_config=$(dump_kernel_config "${kernel_image}");
  # sample kernel_cfg (extracted from kernel_config):
  #  0 1740800 verity %U+1 %U+1 1740800 0 sha1 2ad712bb6..."
  kernel_cfg="$(echo "${kernel_config}" | sed -e 's/.*dm="\([^"]*\)".*/\1/g' |
                cut -f2- -d,)"
  # dm-verity record format: ? sectors ? ? ? ? depth alg hash
  verity_preamble="$(echo "${kernel_config}" |
                     sed -e 's/.*dm="\([^"]*\)".*/\1/g' |
                     cut -f1 -d,)"
  rootfs_sectors=$(echo ${kernel_cfg} | cut -f2 -d' ')
  verity_depth=$(echo ${kernel_cfg} | cut -f7 -d' ')
  verity_algorithm=$(echo ${kernel_cfg} | cut -f8 -d' ')

  # always use the verity binary in the target partition because it may be
  # different.
  mount -o ro "$rootfs_image" "$TMPDIR"
  local verity_path="$TMPDIR/bin/verity"

  alert "Generating hash for $rootfs_image..."
  local generated_verity_info="$($verity_path \
    create \
    "$verity_depth" \
    "$verity_algorithm" \
    "$rootfs_image" \
    "$((rootfs_sectors / 8))" \
    "$TMPFILE")"

  local expected_hash="$(echo ${kernel_cfg} | cut -f9 -d' ')"
  local generated_hash="$(echo "$generated_verity_info" | cut -f9 -d' ')"
  if [ -n "$expected_hash" ] && [ "$expected_hash" = "$generated_hash" ]; then
    alert "SUCCESS: Hash is verified: [$generated_hash]"
    return 0
  else
    alert "FAIL: Hash is different."
    alert "Generated: [$generated_hash], expected: [$expected_hash]"
    return 1
  fi
}

main $@
