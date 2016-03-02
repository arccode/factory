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
TMPFS_SIZE=1024M

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
ASSETS_DIR="/usr/share/chromeos-assets"
MISC_DIR="/usr/share/misc"

PANGO_MODULE="$(pango-querymodules --system |
  awk '$2 == "ModulesPath" {print $NF}')"

# A list of files or directories required to be copied to the wiping tmpfs
# from factory rootfs. The format of each entry is "src_file:dst_file" or
# "src_dir:dst_dir" meaning copy the src_file/src_dir in factory rootfs to
# dst_file/dst_dir in the tmpfs.
FILES_DIRS_COPIED_FROM_ROOTFS="
  ${ASSETS_DIR}/images
  ${ASSETS_DIR}/text/boot_messages
  ${SCRIPT_DIR}/battery_cutoff.sh
  ${SCRIPT_DIR}/common.sh
  ${SCRIPT_DIR}/display_wipe_message.sh
  ${SCRIPT_DIR}/enable_release_partition.sh
  ${SCRIPT_DIR}/generate_finalize_request.sh
  ${SCRIPT_DIR}/inform_shopfloor.sh
  ${SCRIPT_DIR}/wipe_init.sh
  ${PANGO_MODULE}
  ${MISC_DIR}/chromeos-common.sh
  /etc/fonts
  /etc/pango
  /lib/modules
  /usr/share/fonts/notocjk
  /usr/share/cache/fontconfig
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
  activate_date
  backlight_tool
  busybox
  cgpt
  clobber-log
  clobber-state
  coreutils
  crossystem
  dd
  display_boot_message
  dumpe2fs
  ectool
  flashrom
  halt
  initctl
  mkfs.ext4
  mktemp
  mosys
  mount
  od
  pango-view
  pkill
  pv
  reboot
  setterm
  sh
  shutdown
  umount
  vpd
  wget
"

# Include frecon if the system has frecon, otherwice use ply-image instead.
if [ -e /sbin/frecon ]; then
  BIN_DEPS="${BIN_DEPS} /sbin/frecon"
else
  BIN_DEPS="${BIN_DEPS} /usr/bin/ply-image"
fi

# ======================================================================
# Helper functions

die() {
  echo "$@"
  exit 1
}

create_tmpfs_layout() {
  (cd "${TMPFS_PATH}" && mkdir -p ${TMPFS_LAYOUT_DIRS})
  # Create symlinks because some binary programs will call them via full path.
  ln -s . "${TMPFS_PATH}/usr"
  ln -s . "${TMPFS_PATH}/local"
  ln -s bin "${TMPFS_PATH}/sbin"
}

copy_dependent_binary_files() {
  local bin_files=""
  if bin_files="$(which ${BIN_DEPS})"; then
    tar -ch $(lddtree -l ${bin_files} 2>/dev/null | sort -u) |
      tar -C ${TMPFS_PATH} -x
  else
    die "Some requried binary files missing."
  fi
  # Use busybox to install other common utilities.
  # Run the busybox inside tmpfs to prevent 'invalid cross-device link'.
  "${TMPFS_PATH}/bin/busybox" --install "${TMPFS_PATH}/bin"
}

copy_rootfs_files_and_dirs() {
  tar -c ${FILES_DIRS_COPIED_FROM_ROOTFS} | tar -C "${TMPFS_PATH}" -x
}

# ======================================================================
# Main function

main() {
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

set -xe
main "$@"
