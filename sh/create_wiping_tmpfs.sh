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

FACTORY_DIR="/usr/local/factory"
ASSETS_DIR="/usr/share/chromeos-assets"
MISC_DIR="/usr/share/misc"

# A list of files or directories required to be copied to the wiping tmpfs
# from factory rootfs. The format of each entry is "src_file:dst_file" or
# "src_dir:dst_dir" meaning copy the src_file/src_dir in factory rootfs to
# dst_file/dst_dir in the tmpfs.
FILES_DIRS_COPIED_FROM_ROOTFS="
  ${ASSETS_DIR}/images:${ASSETS_DIR}/images
  ${ASSETS_DIR}/text/boot_messages:${ASSETS_DIR}/text/boot_messages
  ${MISC_DIR}/chromeos-common.sh:${MISC_DIR}/chromeos-common.sh
  ${FACTORY_DIR}/misc/wipe_message.png:${FACTORY_DIR}/misc/wipe_message.png
  ${FACTORY_DIR}/sh/common.sh:/bin/common.sh
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
"

# Dependency list of binary programs.
# The busybox dd doesn't support iflag option, so need to copy it from rootfs.
BIN_DEPS="
  /bin/dd
  /bin/mount
  /bin/sh
  /bin/umount
  /sbin/clobber-log
  /sbin/clobber-state
  /sbin/dumpe2fs
  /sbin/frecon
  /sbin/halt
  /sbin/initctl
  /sbin/mkfs.ext4
  /sbin/reboot
  /sbin/shutdown
  /usr/bin/backlight_tool
  /usr/bin/cgpt
  /usr/bin/coreutils
  /usr/bin/crossystem
  /usr/bin/mktemp
  /usr/bin/od
  /usr/bin/pango-view
  /usr/bin/pkill
  /usr/bin/pv
  /usr/bin/setterm
  /usr/local/bin/busybox
  /usr/sbin/display_boot_message
  /usr/sbin/mosys
  ${FACTORY_DIR}/bin/enable_release_partition
  ${FACTORY_DIR}/bin/wipe_init
"

# ======================================================================
# Helper functions

create_tmpfs_layout() {
  (cd "${TMPFS_PATH}" && mkdir -p ${TMPFS_LAYOUT_DIRS})
  # Create symlinks because some binary programs will call them via full path.
  ln -s . "${TMPFS_PATH}/usr"
  ln -s bin "${TMPFS_PATH}/sbin"
}

copy_dependent_binary_files() {
  local bin file dirname
  for bin in ${BIN_DEPS}; do
    cp -f "${bin}" "${TMPFS_PATH}/bin/."
    # Copy the dependent .so files into $TMPFS_PATH/lib/.
    for file in $(lddtree -l "${bin}"); do
      dirname=$(dirname "${file}")
      mkdir -p "${TMPFS_PATH}/${dirname}"
      cp -L "${file}" "${TMPFS_PATH}/${dirname}"
    done
  done
  # Use busybox to install other common utilities.
  # Run the busybox inside tmpfs to prevent 'invalid cross-device link'.
  "${TMPFS_PATH}/bin/busybox" --install "${TMPFS_PATH}/bin"
}

copy_rootfs_files_and_dirs() {
  local layout src_file dst_file dst_dir
  # Copy some files from factory rootfs to the wiping tmpfs.
  for layout in ${FILES_DIRS_COPIED_FROM_ROOTFS}; do
    src_file="${layout%:*}"
    dst_file="${layout#*:}"
    dst_dir=$(dirname "${dst_file}")

    mkdir -p "${TMPFS_PATH}/${dst_dir}"
    cp -rf "${src_file}" "${TMPFS_PATH}/${dst_dir}"
  done
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

  create_tmpfs_layout
  copy_dependent_binary_files
  copy_rootfs_files_and_dirs
}

main "$@"
