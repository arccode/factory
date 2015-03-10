#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script performs the following tasks to create a tmpfs for
# factory wiping:
# - Mount a tmpfs under $1.
# - Create directories in the tmpfs.
# - Copy dependent files (scripts, binary executables and image files)
#   from rootfs to tmpfs.

# ======================================================================
# Constants

TMPFS_PATH="$1"
TMPFS_SIZE=100M

SCRIPT_DIR="/usr/local/factory/sh"
COMMON_SCRIPT_SOURCE="/usr/share/misc/chromeos-common.sh"
COMMON_SCRIPT_TARGET="${TMPFS_PATH}/usr/share/misc/chromeos-common.sh"

# A list of standalone files required to copy to the wiping tmpfs
# from factory rootfs. The format of each entry is "src_file:dst_file"
# meaning copy the src_file in factory rootfs to dst_file in the tmpfs.
STANDALONE_FILES="
  ${COMMON_SCRIPT_SOURCE}:${COMMON_SCRIPT_TARGET}
"

# Layout of directories to be created in tmpfs
TMPFS_LAYOUT_DIRS="
  bin
  dev
  etc
  lib
  log
  mnt/stateful_partition
  proc
  root
  sys
  tmp
  usr/share/misc
"

# Dependency list of binary programs.
# The busybox dd doesn't support iflag option, so need to copy it from rootfs.
BIN_DEPS="
  /bin/dd
  /bin/sh
  /sbin/clobber-log
  /sbin/clobber-state
  /sbin/dumpe2fs
  /sbin/initctl
  /sbin/mkfs.ext4
  /sbin/shutdown
  /usr/bin/backlight_tool
  /usr/bin/cgpt
  /usr/bin/coreutils
  /usr/bin/crossystem
  /usr/bin/pango-view
  /usr/bin/pv
  /usr/bin/setterm
  /usr/local/bin/busybox
  /usr/sbin/display_boot_message
  ${SCRIPT_DIR}/common.sh
  ${SCRIPT_DIR}/enable_release_partition.sh
  ${SCRIPT_DIR}/wipe_init.sh
"

# ======================================================================
# Helper functions

copy_dependent_binary_files() {
  local bin file dirname
  for bin in ${BIN_DEPS}; do
    cp -f "${bin}" "${TMPFS_PATH}/bin/."
    # Copy the dependent .so files into $TMPFS_PATH/lib/.
    for file in $(lddtree -l "${bin}"); do
      dirname=$(dirname "${file}")
      mkdir -p "${TMPFS_PATH}/${dirname}"
      cp "${file}" "${TMPFS_PATH}/${dirname}"
    done
  done
  # Use busybox to install other common utilities.
  # Run the busybox inside tmpfs to prevent 'invalid cross-device link'.
  "${TMPFS_PATH}/bin/busybox" --install "${TMPFS_PATH}/bin"
}

copy_standalone_files() {
  local layout src_file dst_file dst_dir
  # Copy some files from factory rootfs to the wiping tmpfs.
  for layout in ${STANDALONE_FILES}; do
    src_file="${layout%:*}"
    dst_file="${layout#*:}"
    dst_dir=$(dirname "${dst_file}")

    [ -d "${dst_dir}" ] || mkdir -p "${dst_dir}"
    cp -f "${src_file}" "${dst_file}"
  done
}

hack_clobber_state() {
  # We use chroot to invoke wiping related scripts in a tmpfs and still
  # need to keep some files in the factory rootfs during wiping,
  # ex: /dev /proc /sys, etc.
  # Delete the lines of wiping factory rootfs in clobber-state.
  # Otherwise, it will get stuck in shutdown command after wiping.

  # Note that when invoking clobber-state for factory wiping,
  # OTHER_ROOT_DEV is factory rootfs and ROOT_DEV is release rootfs.
  # We'll alter clobber-state behavior by overriding ROOT_DEV before
  # invoking it.
  local clobber_file="${TMPFS_PATH}/bin/clobber-state"
  sed -i '/dd bs=4M count=1 if=\/dev\/zero of=${OTHER_ROOT_DEV}/d' \
    "${clobber_file}"
  sed -i '/wipedev ${OTHER_ROOT_DEV}/d' "${clobber_file}"
}

# ======================================================================
# Main function

main() {
  set -xe
  if [ "$#" != "1" ]; then
    echo "Usage: $0 TMPFS_PATH"
    exit 1
  fi

  mkdir -p "${TMPFS_PATH}"
  mount -n -t tmpfs -o "size=${TMPFS_SIZE}" tmpfs "${TMPFS_PATH}"

  # Create symlinks because some binary programs will call them via full path.
  ln -s . "${TMPFS_PATH}/usr"
  ln -s bin "${TMPFS_PATH}/sbin"

  (cd "${TMPFS_PATH}" && mkdir -p ${TMPFS_LAYOUT_DIRS})
  copy_dependent_binary_files
  copy_standalone_files
  hack_clobber_state
}

main "$@"
