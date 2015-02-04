#!/bin/bash

# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Script to change file system size on a Chromium OS disk image.

. "$(dirname "$(readlink -f "$0")")/factory_common.sh" || exit 1

# Flags
DEFINE_string image "" \
  "Path to ChromiumOS image: /path/chromiumos_image.bin" "i"
DEFINE_integer partition_index "1" \
  "Index of partition that has the target file system." "p"
DEFINE_integer size_mb "1024" \
  "New file system size in MB." "s"

# Parse command line
FLAGS "$@" || exit 1
ORIGINAL_PARAMS="$@"
eval set -- "${FLAGS_ARGV}"

MAPPED_IMAGE=""

on_exit() {
  image_clean_temp
  if [ -n "${MAPPED_IMAGE}" ]; then
    image_unmap_partition "${MAPPED_IMAGE}"
  fi
}

# Param checking and validation
check_file_param() {
  local param="$1"
  local msg="$2"
  local param_name="${param#FLAGS_}"
  local param_value="$(eval echo \$$1)"

  [ -n "${param_value}" ] ||
    die "You must assign a file for --${param_name} ${msg}"
  [ -f "${param_value}" ] ||
    die "Cannot find file: $param_value"
}

check_parameters() {
  check_file_param FLAGS_image ""
}

# Resizes file system on given partition of disk image.
resize_filesystem() {
  local image="$(readlink -f "$1")"
  local index="$2"
  local new_size="$3"

  local partition="$(image_map_partition "${image}" "${index}")" ||
    die "Cannot access partition ${index} on image ${image} ."
  MAPPED_IMAGE="${partition}"

  # Decide new size.
  info "Checking existing file system size..."
  local block_count="$(sudo dumpe2fs -h "${partition}" | grep '^Block count:')"
  local block_size="$(sudo dumpe2fs -h "${partition}" | grep '^Block size:')"
  block_count="${block_count##* }"
  block_size="${block_size##* }"
  local size_mb="$((block_count * block_size / 1048576))" ||
    die "Failed to calculate file system size (${block_count}, ${block_size})"
  info "${image}#${index}: ${size_mb}MBs."

  # File system must be clean before we perform resize2fs.
  sudo fsck -y "${partition}"
  sudo resize2fs -f "${partition}" "${new_size}M" ||
    die "Failed to resize file system to ${new_size} MBs."

  image_unmap_partition "${partition}"
  MAPPED_IMAGE=""
  info "File system on ${image}#${index} has been resize to ${new_size} MBs."
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

  resize_filesystem "${FLAGS_image}" "${FLAGS_partition_index}" \
    "${FLAGS_size_mb}"
}

main "$@"
