#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# The /var is by default mounted as encrypted, using 1/10 of total stateful
# partition (/mnt/stateful_partition/encrypted.block). If stateful partition
# size is changed, the encrypted block won't change unless it's deleted (or
# key changed). Since the stateful partition of a factory image is usually
# 1GB, the encrypted block will be only 100MB and is usually not enough for
# factory data (/var/factory). Considering that we will wipe data during
# finalization and the factory data does not have user privacy, it seems
# reasonable to redirect factory data (/var/factory) to the unencrypted path on
# stateful parition.

STATEFUL="/mnt/stateful_partition"

main() {
  local overlay="${STATEFUL}/var/factory"
  local dest="/var/factory"

  if [ ! -e /dev/mapper/encstateful ]; then
    return
  fi

  # Ensure the mount point still exist.
  mkdir -p "${dest}"

  if [ ! -d "${overlay}" ]; then
    # Safely migrate from existing (or newly created) /var/factory.
    mkdir -p "$(dirname "${overlay}")"
    mv "${dest}" "${overlay}"
    mkdir -p "${dest}"
  fi

  # We use mount-bind instead of symlink because there are already many programs
  # (factory_bug, dut_upload, ...) assuming the factory data can be simply
  # collected using tar without solving symlinks.
  mount --bind "${overlay}" "${dest}"
}

main "$@"
