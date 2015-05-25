#!/bin/sh

# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Script to generate an universal installation image (usually used for factory
# install or RMA purpose), by merging multiple images signed by different keys.
# CAUTION: Recovery shim images are not supported yet because they require the
# kernel partitions to be laid out in a special way

. "$(dirname "$(readlink -f "$0")")/factory_common.sh" || exit 1

# Temp file to store layout, will be removed at exit.
LAYOUT_FILE="$(mktemp --tmpdir)"

# Special name for creating dummy partitions in layout file.
DUMMY_FILE_NAME="@DUMMYFILE@"


alert() {
  echo "$*" >&2
}

die() {
  alert "ERROR: $*"
  exit 1
}

on_exit() {
  rm -f "$LAYOUT_FILE"
}

# Processes a logical disk image layout description file.
# Each entry in layout is a "file:partnum" entry (:partnum is optional),
# referring to the #partnum partition in file.
# The index starts at one, referring to the first partition in layout.
image_process_layout() {
  local layout_file="$1"
  local callback="$2"
  shift
  shift
  local param="$@"
  local index=0

  while read layout; do
    local image_file="${layout%:*}"
    local part_num="${layout#*:}"
    index="$((index + 1))"
    [ "$image_file" != "$layout" ] || part_num=""

    "$callback" "$image_file" "$part_num" "$index" "$param"
  done <"$layout_file"
}

# Callback of image_process_layout. Returns the size (in sectors) of given
# object (partition in image or file).
layout_get_sectors() {
  local image_file="$1"
  local part_num="$2"
  local aligned_size_in_bytes

  if [ "$image_file" = "$DUMMY_FILE_NAME" ]; then
    echo 1
  elif [ -n "$part_num" ]; then
    image_part_size "$image_file" "$part_num"
  else
    aligned_size_in_bytes="$(image_alignment "$(stat -c"%s" "$image_file")" \
                                             "$IMAGE_CGPT_BS" "")"
    echo $((aligned_size_in_bytes / IMAGE_CGPT_BS))
  fi
}

# Callback of image_process_layout. Copies an input source object (file or
# partition) into specified partition on output file.
layout_copy_partition() {
  local input_file="$1"
  local input_part="$2"
  local output_part="$3"
  local output_file="$4"
  alert "$(basename "$input_file"):$input_part =>" \
        "$(basename "$output_file"):$output_part"

  if [ "$input_file" = "$DUMMY_FILE_NAME" ]; then
    true  # do nothing
  elif [ -n "$input_part" ]; then
    image_partition_copy "$input_file" "$input_part" \
                         "$output_file" "$output_part"
    # Update partition type information
    local partition_type="$(cgpt show -q -n -t -i "$input_part" "$input_file")"
    local partition_attr="$(cgpt show -q -n -A -i "$input_part" "$input_file")"
    local partition_label="$(cgpt show -q -n -l -i "$input_part" "$input_file")"
    local partition_guid="$(cgpt show -q -n -u -i "$input_part" "$input_file")"
    cgpt add -t "$partition_type" -l "$partition_label" -A "$partition_attr" \
             -u "$partition_guid" -i "$output_part" "$output_file"
  else
    image_update_partition "$output_file" "$output_part" <"$input_file"
  fi
}

build_image_file() {
  local layout_file="$1"
  local output_file="$2"
  local sectors_list

  # Check and obtain size information from input sources
  sectors_list="$(image_process_layout "$layout_file" layout_get_sectors)"

  image_geometry_build_file "$sectors_list" "$output_file"

  # Copy partitions content
  image_process_layout "$layout_file" layout_copy_partition "$output_file"
}

# Add kernel-rootfs pair from image source to layout file.
add_kernel_rootfs_pair() {
  local layout_file="$1"
  local image_source="$2"

  local kernel_source="$image_source:2"
  local rootfs_source="$image_source:3"
  echo "$kernel_source" >>"$layout_file"
  echo "$rootfs_source" >>"$layout_file"
}

add_dummy_kernel_rootfs_pair() {
  local layout_file="$1"

  local kernel_source="$DUMMY_FILE_NAME"
  local rootfs_source="$DUMMY_FILE_NAME"
  echo "$kernel_source" >>"$layout_file"
  echo "$rootfs_source" >>"$layout_file"
}

# Creates standard multiple image layout
create_standard_layout() {
  local main_source="$1"
  local layout_file="$2"
  local image index
  shift
  shift

  for image in "$main_source" "$@"; do
    if [ ! -f "$image" ]; then
      die "Cannot find input file $image."
    fi
  done

  echo "$main_source:1" >>"$layout_file"  # stateful partition

  # Adding must-have kernel-rootfs pairs. There are 3 must-have pairs, namely:
  # partition 2-3, 4-5, and 6-7.
  local must_have_kernel_rootfs_pairs="3"
  for index in $(seq 1 $must_have_kernel_rootfs_pairs); do
    if [ "$#" -eq 0 ]; then
      add_dummy_kernel_rootfs_pair "$layout_file"
    else
      # TODO(hungte) detect if input source is a recovery/USB image
      add_kernel_rootfs_pair "$layout_file" "$1"
      shift
    fi
  done

  # Adding legacy partitions 8 to 12. They're OEM, reserved, reserved, RWFW,
  # EFI respectively.
  local legacy_partitions="$(seq 8 12)"
  for index in $legacy_partitions; do
    local partition_source="$DUMMY_FILE_NAME"
    local size="$(cgpt show -s -i $index "$main_source")"
    if [ "$size" -ne "0" ]; then
      partition_source="$main_source:$index"
    fi
    echo "$partition_source" >>"$layout_file"
  done

  # Adding additional partitions if needed.
  while [ "$#" -gt 0 ]; do
    add_kernel_rootfs_pair "$layout_file" "$1"
    shift
  done
}

usage_die() {
  alert "Usage: $SCRIPT [-m master] [-f] output shim1 [shim2 shim3 ...]"
  alert "   or  $SCRIPT -l layout [-f] output"
  exit 1
}

main() {
  local force=""
  local image=""
  local output=""
  local main_source=""
  local index=""
  local slots="0"
  local layout_mode=""

  while [ "$#" -gt 1 ]; do
    case "$1" in
      "-f" )
        force="True"
        shift
        ;;
      "-m" )
        main_source="$2"
        shift
        shift
        ;;
      "-l" )
        cat "$2" >"$LAYOUT_FILE"
        layout_mode="TRUE"
        shift
        shift
        ;;
      * )
        break
    esac
  done

  if [ -n "$layout_mode" ]; then
    [ "$#" = 1 ] || usage_die
  elif [ "$#" -lt 2 ]; then
    alert "ERROR: invalid number of parameters ($#)."
    usage_die
  fi

  if [ -z "$main_source" ]; then
    main_source="$2"
  fi
  output="$1"
  shift

  if [ -f "$output" -a -z "$force" ]; then
    die "Output file $output already exists. To overwrite the file, add -f."
  fi

  if [ -z "$layout_mode" ]; then
    create_standard_layout "$main_source" "$LAYOUT_FILE" "$@"
  fi
  build_image_file "$LAYOUT_FILE" "$output"
  echo ""
  echo "Image created: $output"
}

set -e
trap on_exit EXIT
main "$@"
