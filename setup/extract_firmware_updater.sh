#!/bin/bash

# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Script to extract a firmware updater (and firmware blobs) from a signed
# recovery image.

. "$(dirname "$(readlink -f "$0")")/factory_common.sh" || exit 1

# Flags
DEFINE_string image "" \
  "Path to release image: /path/chromiumos_image.bin" "i"
DEFINE_string output_dir "." "Directory to save output file(s)." "o"

# Parse command line
FLAGS "$@" || exit 1
ORIGINAL_PARAMS="$@"
eval set -- "${FLAGS_ARGV}"

on_exit() {
  image_clean_temp
}

# Param checking and validation
check_file_param() {
  local param="$1"
  local msg="$2"
  local param_name="${param#FLAGS_}"
  local param_value="$(eval echo \$$1)"

  [ -n "$param_value" ] ||
    die "You must assign a file for --$param_name $msg"
  [ -f "$param_value" ] ||
    die "Cannot find file: $param_value"
}

check_parameters() {
  check_file_param FLAGS_image ""
}

# Extracts firmware updater from specified disk image file.
extract_firmware_updater() {
  local image="$(readlink -f "$1")"
  local output_dir="$(readlink -f "$2")"

  local fwupdater="$output_dir/chromeos-firmwareupdate"
  local temp_mount="$(mktemp -d --tmpdir)"
  local updater_path="/usr/sbin/chromeos-firmwareupdate"
  local src_file="$temp_mount$updater_path"
  image_add_temp "$temp_mount"

  # 'ext2' is required to prevent accidentally modifying image
  image_mount_partition "$image" "3" "$temp_mount" "ro" "-t ext2" ||
    die "Cannot mount partition #3 (rootfs) in release image: $image"
  [ -f "$src_file" ] ||
    die "No firmware updater in release image: $image"
  cp -f "$src_file" "$fwupdater" ||
    die "Failed to copy file from release image $image to $fwupdater."
  image_umount_partition "$temp_mount"
  info "Firmware updater saved in: $fwupdater"
}

main() {
  set -e
  trap on_exit EXIT
  if [ "$#" != 0 ]; then
    flags_help
    exit 1
  fi

  check_parameters
  # Check required tools.
  if ! image_has_part_tools; then
    die "Missing partition tools. Please install cgpt/parted, or run in chroot."
  fi

  extract_firmware_updater "$FLAGS_image" "$FLAGS_output_dir"
}

main "$@"
