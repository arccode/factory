#!/bin/sh
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Symlinks are by default disabled on Chrome OS since
# https://chromium-review.googlesource.com/966683.
# However, for factory we do want to allow symlink everywhere so 3rd party
# programs won't have trouble. Also for b/74420122.

# See platform2/init/chromeos_startup for the details.

LSM_INODE_POLICIES="/sys/kernel/security/chromiumos/inode_security_policies"

unmount_security_fs() {
  umount /sys/kernel/security || true
}

main() {
  local need_umount=""
  if [ ! -e "${LSM_INODE_POLICIES}" ]; then
    mount -n -t securityfs -o nodev,noexec,nosuid securityfs \
      /sys/kernel/security && trap unmount_security_fs EXIT
  fi

  if [ -e "${LSM_INODE_POLICIES}" ]; then
    # /var/factory may be already covered by /var, but we do want to allow it
    # explicitly in case if other init jobs mounted /var/factory in different
    # location.
    for path in /var /var/factory /mnt/stateful_partition; do
      printf "${path}" >"${LSM_INODE_POLICIES}/allow_symlink"
      printf "${path}" >"${LSM_INODE_POLICIES}/allow_fifo"
    done
  fi
}

main "$@"
