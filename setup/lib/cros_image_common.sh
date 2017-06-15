#!/bin/bash

# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script contains common utility function to deal with disk images,
# especially for being redistributed into platforms without complete Chromium OS
# developing environment.

# CGPT Header: PMBR, header, table; sec_table, sec_header
IMAGE_CGPT_START_SIZE=$((1 + 1 + 32))
IMAGE_CGPT_END_SIZE=$((32 + 1))
IMAGE_CGPT_BS="512"
: ${CGPT:=}
: ${SUDO:=}

# Alignment of partition sectors
IMAGE_PARTITION_SECTOR_ALIGNMENT=256

# Checks if given command is available in current system
image_has_command() {
  type "$1" >/dev/null 2>&1
}

# Prints error message and exit as 1 (error)
image_die() {
  echo "ERROR: $@" >&2
  exit 1
}

# Finds and checks if CGPT is available. Similar to image_check_part_tools, but
# this is dedicated for 'cgpt' since it's the only tool (currently) that can
# create and modify ChromeOS style partitions.
image_check_cgpt() {
  if [ -z "${CGPT}" ]; then
    image_die "Need cgpt utility."
  fi
}

# Finds and checks if the system has tools to do partitioning.
image_check_part_tools() {
  if image_has_command python || [ -n "${CGPT}" ] || image_has_command parted;
  then
    return
  else
    die "Missing partition tools. " \
         "Please install Python or parted or cgpt, or run inside chroot."
  fi
}

# Finds a tool program in PATH or given folder(s), and prints the found path.
image_find_tool() {
  local tool="$1" dir=""
  if image_has_command "${tool}"; then
    echo "${tool}"
    return
  fi
  shift
  for dir in "$@"; do
    if [ -x "${dir}/${tool}" ]; then
      echo "$(readlink -f "${dir}/${tool}")"
      return
    fi
  done
}

# Returns offset aligned to alignment.
# If size is given, only align if size >= alignment.
image_alignment() {
  local offset="$1"
  local alignment="$2"
  local size="$3"

  # If size is assigned, align only if the new size is larger then alignment.
  if [ "$((offset % alignment))" != "0" ]; then
    if [ -z "$size" ] || [ "$size" -ge "$alignment" ]; then
      offset=$((offset + alignment - (offset % alignment)))
    fi
  fi
  echo "$((offset))"
}

# Finds the best partition tool and print partition offset
image_part_offset() {
  local file="$1"
  local partno="$2"
  local unpack_file="$(dirname "$file")/unpack_partitions.sh"

  if image_has_command python; then
    ${SUDO} python "${SCRIPT_DIR}/pygpt" show -b -i "${partno}" "${file}"
  elif [ -n "${CGPT}" ]; then
    ${SUDO} "${CGPT}" show -b -i "$partno" "$file"
  elif image_has_command parted; then
    # First trial-run to make sure image is valid (because awk always return 0)
    ${SUDO} parted -m "$file" unit s print | grep -qs "^$partno:" || exit 1
    ${SUDO} parted -m "$file" unit s print | \
      awk -F ':' "/^$partno:/ { print int(\$2) }"
  elif [ -f "$unpack_file" ]; then
    awk "/ $partno  *Label:/ { print \$2 }" "$unpack_file"
  else
    exit 1
  fi
}

# Finds the best partition tool and print partition size
image_part_size() {
  local file="$1"
  local partno="$2"
  local unpack_file="$(dirname "$file")/unpack_partitions.sh"

  if image_has_command python; then
    ${SUDO} python "${SCRIPT_DIR}/pygpt" show -s -i "${partno}" "${file}"
  elif [ -n "${CGPT}" ]; then
    ${SUDO} "${CGPT}" show -s -i "$partno" "$file"
  elif image_has_command parted; then
    # First trial-run to make sure image is valid (because awk always return 0)
    ${SUDO} parted -m "$file" unit s print | grep -qs "^$partno:" || exit 1
    ${SUDO} parted -m "$file" unit s print | \
      awk -F ':' "/^$partno:/ { print int(\$4) }"
  elif [ -s "$unpack_file" ]; then
    awk "/ $partno  *Label:/ { print \$3 }" "$unpack_file"
  else
    exit 1
  fi
}

# Callback of image_process_geometry. Prints the proper offset of current
# partition by give offset and size.
image_geometry_get_partition_offset() {
  local offset="$1"
  local sectors="$2"
  local index="$3"

  image_alignment "$offset" "$IMAGE_PARTITION_SECTOR_ALIGNMENT" "$sectors"
}

# Callback of image_process_geometry. Creates a partition by give offset,
# size (sectors), and index.
image_geometry_create_partition() {
  local offset="$1"
  local sectors="$2"
  local index="$3"
  local output_file="$4"

  if [ "$offset" = "0" ]; then
    # first entry is CGPT; ignore.
    return
  fi

  image_check_cgpt
  "${CGPT}" add -b "$offset" -s "$sectors" -i "$index" -t reserved "$output_file"
}

# Processes a list of disk geometry sectors into aligned (offset, sectors) form.
# The index starts at zero, referring to the partition table object itself.
image_process_geometry() {
  local sectors_list="$1"
  local callback="$2"
  shift
  shift
  local param="$@"
  local offset=0 sectors
  local index=0

  for sectors in $sectors_list; do
    offset="$(image_alignment \
              $offset $IMAGE_PARTITION_SECTOR_ALIGNMENT $sectors)"
    "$callback" "$offset" "$sectors" "$index" $param
    offset="$((offset + sectors))"
    index="$((index + 1))"
  done
}

# Create a cgpt image file based on a list of disk geometry sectors in
# (offset, sectors) form. The form doesn't have to be aligned since this
# funciton will process it. Each partition will be formatted to
# cgpt data partition with $part_filesystem if it's specified.
image_geometry_build_file() {
  local sectors_list="$1"
  local output_file="$2"
  local part_filesystem="$3"

  local output_file_size=0
  local partition_offsets

  image_check_cgpt

  # Calculate output image file size
  partition_offsets="$(image_process_geometry \
      "$IMAGE_CGPT_START_SIZE $sectors_list $IMAGE_CGPT_END_SIZE 1" \
      image_geometry_get_partition_offset)"
  output_file_size="$(echo "$partition_offsets" | tail -n 1)"

  # Create empty image file
  truncate -s "0" "$output_file"  # starting with a new file is much faster.
  truncate -s "$((output_file_size * IMAGE_CGPT_BS))" "$output_file"

  # Initialize partition table (GPT)
  "${CGPT}" create "$output_file"
  "${CGPT}" boot -p "$output_file" >/dev/null

  # Create partition tables
  image_process_geometry "$IMAGE_CGPT_START_SIZE $sectors_list" \
                         image_geometry_create_partition \
                         "$output_file"
}

# Dumps a file by given offset and size (in sectors)
image_dump_partial_file() {
  local file="$1"
  local offset="$2"
  local sectors="$3"
  local bs=512

  # Increase buffer size as much as possible until 8M
  while [ $((bs < (8 * 1024 * 1024) && sectors > 0 &&
             offset % 2 == 0 && sectors % 2 == 0)) = "1" ]; do
    bs=$((bs * 2))
    offset=$((offset / 2))
    sectors=$((sectors / 2))
  done

  if image_has_command pv; then
    dd if="$file" bs=$bs skip="$offset" count="$sectors" \
      oflag=sync status=noxfer 2>/dev/null |
      pv -ptreb -B $bs -s $((sectors * bs))
  else
    dd if="$file" bs=$bs skip="$offset" count="$sectors" \
      oflag=sync status=noxfer 2>/dev/null
  fi
}

# Dumps a specific partition from given image file
image_dump_partition() {
  local file="$1"
  local part_num="$2"
  local offset="$(image_part_offset "$file" "$part_num")" ||
    image_die "failed to find partition #$part_num from: $file"
  local size="$(image_part_size "$file" "$part_num")" ||
    image_die "failed to find partition #$part_num from: $file"

  image_dump_partial_file "$file" "$offset" "$size"
}

# Updates a file (from stdin) by given offset and size (in sectors)
image_update_partial_file() {
  local file="$1"
  local offset="$2"
  local sectors="$3"
  local bs=512
  local oflag="oflag=dsync"

  # Improve performance if we're not updating block (Ex, USB) devices
  [ -b "$file" ] || oflag=""

  # Increase buffer size as much as possible until 8M
  while [ $((bs < (8 * 1024 * 1024) && sectors > 0 &&
             offset % 2 == 0 && sectors % 2 == 0)) = "1" ]; do
    bs=$((bs * 2))
    offset=$((offset / 2))
    sectors=$((sectors / 2))
  done

  if image_has_command pv; then
    pv -ptreb -B $bs -s $((sectors * bs)) |
      dd of="$file" bs=$bs seek="$offset" count="$sectors" \
        iflag=fullblock $oflag conv=notrunc status=noxfer 2>/dev/null
  else
    dd of="$file" bs=$bs seek="$offset" count="$sectors" \
      iflag=fullblock $oflag conv=notrunc status=noxfer 2>/dev/null
  fi
}

# Updates a specific partition in given image file (from stdin)
image_update_partition() {
  local file="$1"
  local part_num="$2"
  local offset="$(image_part_offset "$file" "$part_num")" ||
    image_die "failed to find partition #$part_num from: $file"
  local size="$(image_part_size "$file" "$part_num")" ||
    image_die "failed to find partition #$part_num from: $file"

  image_update_partial_file "$file" "$offset" "$size"
}

# Maps a specific partition from given image file to a loop device
image_map_partition() {
  local file="$1"
  local part_num="$2"
  local offset="$(image_part_offset "$file" "$part_num")" ||
    image_die "failed to find partition #$part_num from: $file"
  local size="$(image_part_size "$file" "$part_num")" ||
    image_die "failed to find partition #$part_num from: $file"

  sudo losetup --offset $((offset * 512)) --sizelimit=$((size * 512)) \
    -f --show "$file"
}

# Unmaps a loop device created by image_map_partition
image_unmap_partition() {
  local map_point="$1"

  sudo losetup -d "$map_point"
}

# Mounts a specific partition inside a given image file
image_mount_partition() {
  local file="$1"
  local part_num="$2"
  local mount_point="$3"
  local mount_opt="$4"
  local mount_ext="$5"
  local offset="$(SUDO=sudo image_part_offset "$file" "$part_num")" ||
    image_die "failed to find partition #$part_num from: $file"
  local size="$(SUDO=sudo image_part_size "$file" "$part_num")" ||
    image_die "failed to find partition #$part_num from: $file"

  if [ -z "$mount_opt" ]; then
    # by default, mount as read-only.
    mount_opt=",ro"
  else
    mount_opt=",$mount_opt"
  fi

  sudo mount \
    -o "loop,offset=$((offset * 512)),sizelimit=$((size * 512))$mount_opt" \
    $mount_ext \
    "$file" \
    "$mount_point"
}

# Unmounts a partition mount point by mount_partition
image_umount_partition() {
  local mount_point="$1"

  sudo umount "$mount_point"
}

# Copy a partition from one image to another (size must be equal)
image_partition_copy() {
  local src="$1" src_part="$2" dst="$3" dst_part="$4"
  local size1="$(image_part_size "$src" "$src_part")"
  local size2="$(image_part_size "$dst" "$dst_part")"
  if [ "$size1" != "$size2" ]; then
    die "Partition size different: ($size1 != $size2)"
  fi
  image_dump_partition "$src" "$src_part" 2>/dev/null |
    image_update_partition "$dst" "$dst_part"
}

# Copy a partition from one image to another (source <= dest)
image_partition_overwrite() {
  local src="$1" src_part="$2" dst="$3" dst_part="$4"
  local size1="$(image_part_size "$src" "$src_part")"
  local size2="$(image_part_size "$dst" "$dst_part")"
  if [ "$size1" -gt "$size2" ]; then
    die "Destination is too small: ($size1 > $size2)"
  fi
  image_dump_partition "$src" "$src_part" 2>/dev/null |
    image_update_partition "$dst" "$dst_part"
}

# Copy a partition image from file to a full disk image.
image_partition_copy_from_file() {
  local src="$1" dst="$2" dst_part="$3"
  local size1="$(($(stat -c"%s" "$src") / 512))"
  local size2="$(image_part_size "$dst" "$dst_part")"
  if [ "$size1" != "$size2" ]; then
    die "Partition size different: ($size1 != $size2)"
  fi
  image_update_partition "$dst" "$dst_part" <"$src"
}

# Temporary object management
_IMAGE_TEMP_OBJECTS=""

# Add a temporary object (by mktemp) into list for image_clean_temp to clean
image_add_temp() {
  _IMAGE_TEMP_OBJECTS="$_IMAGE_TEMP_OBJECTS $*"
}

# Cleans objects tracked by image_add_temp.
image_clean_temp() {
  local temp_list="$_IMAGE_TEMP_OBJECTS"
  local object
  _IMAGE_TEMP_OBJECTS=""

  for object in $temp_list; do
    if [ -d "$object" ]; then
      sudo umount "$object" >/dev/null 2>&1 || true
      sudo rm -rf "$object" >/dev/null 2>&1 || true
    else
      rm -f "$object" >/dev/null 2>&1 || true
    fi
  done
}
