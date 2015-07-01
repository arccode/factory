#!/bin/sh

# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Script to extract image resources from multiple images and then compress
# and save them into a single output image.

. "$(dirname "$(readlink -f "$0")")/factory_common.sh" || exit 1

# Flags
DEFINE_string save_partitions "1,4,5,6,7,8,12" \
  "A list of numbers specifying partitions to be compressed from \
each input image."
DEFINE_string format "ext4" \
  "Filesystem format of the output file, ex: ext3, ext4, fat, msdos, etc."
DEFINE_string output "resources.ext4" \
  "File name of the output image."
DEFINE_boolean force ${FLAGS_FALSE} "Try to force update." ""

# Parse command line
FLAGS "$@" || exit 1
ORIGINAL_PARAMS="$@"
eval set -- "${FLAGS_ARGV}"

# Temp folder to store the compressed partitions for each images.
INSTALLER_RESOURCES_DIR="$(mktemp -d)"

# Partition number on the output file storing compressed input partitions.
DATA_PART_NUM=1

alert() {
  echo "$*" >&2
}

die() {
  alert "ERROR: $*"
  exit 1
}

on_exit() {
  image_clean_temp
  rm -rf "${INSTALLER_RESOURCES_DIR}"
}

# Usage: compress_one_partition <image_file> <part_num> <output_dir>
# Args:
#   image_file: The image file.
#   part_num: The partition number to make filesystem on it.
#   output_dir: The output directory to store the compressed partition
compress_one_partition() {
  local image_file="$1"
  local part_num="$2"
  local output_dir="$3"
  local part_hash

  mkdir -p "${output_dir}" || die "Cannot create directory: ${output_dir}."

  alert "Compressing partition ${part_num} of ${image_file}..."
  part_hash="$(compress_and_hash_partition \
      "${image_file}" "${part_num}" "${output_dir}/${part_num}.gz")"

  # The compress_and_hash_partition returns the hash of the compressed
  # file but it doesn't guarantee the copy to destination is completed.
  # Verifies the hash of the destination file to ensure the copy is
  # completed and throws error if the hash verification failed.
  actual_hash=$(openssl sha1 -binary "${output_dir}/${part_num}.gz" |
                openssl base64)
  [ "${part_hash}" = "${actual_hash}" ] ||
      die "Failed to generate ${output_dir}/${part_num}.gz."

  echo "${part_num}_checksum = ${part_hash}" >> "${output_dir}/config"
}

# Compress partitions of each image to folder ${INSTALLER_RESOURCES_DIR}.
# Usage: compress_partitions <save_partitions> <image1> <image2> ...
# Args:
#   save_partitions: a list of number specifying which partitions to compress.
#     For example: "1,4,5,6,7"
#   imageN: the input images to be compressed
compress_partitions() {
  local save_partitions="$1,"
  shift
  local image next_part partitions_list
  local kern_guid
  local compressed_size_in_bytes overhead_in_bytes
  local filesystem_overhead_fraction=7  # Add extra 1 / 7 size for overhead.

  for image in "$@"; do
    if [ ! -f "${image}" ]; then
      die "Cannot find input file ${image}."
    fi
  done

  for image in "$@"; do
    # Use GUID of installer kernel (partition 2) as the directory name to
    # store the compressed partitions of the image.
    kern_guid="$(cgpt show -u -i 2 "${image}")"

    partitions_list="${save_partitions}"
    # Compress each partition to the shared folder.
    next_part=${partitions_list%%,*}
    while [ $((next_part)) -ne 0 ]; do
      compress_one_partition "${image}" "$((next_part))" \
                             "${INSTALLER_RESOURCES_DIR}/${kern_guid}"
      partitions_list=${partitions_list#*,}
      next_part=${partitions_list%%,*}
    done
  done

  # Count the total size of the compressed files.
  # Then plus extra size for filesystem overhead.
  compressed_size_in_bytes=$(du -sb "${INSTALLER_RESOURCES_DIR}" | cut -f1)
  overhead_in_bytes=$((compressed_size_in_bytes / filesystem_overhead_fraction))
  echo "$((compressed_size_in_bytes + overhead_in_bytes))"
}

# Convert a list of partition sizes in bytes to a list of sizes in sectors.
bytes_to_sectors_list() {
  local bytes_list="$1,"
  local sectors_list=""
  local part_bytes part_sectors
  local aligned_bytes

  # Convert bytes_list to sectors_list
  part_bytes=${bytes_list%%,*}
  while [ $((part_bytes)) -ne 0 ]; do
    aligned_bytes=$(image_alignment "${part_bytes}" "${IMAGE_CGPT_BS}" "")
    part_sectors=$((aligned_bytes / IMAGE_CGPT_BS))
    sectors_list="${sectors_list} ${part_sectors}"

    # Continue on remaining partitions.
    bytes_list=${bytes_list#*,}
    part_bytes=${bytes_list%%,*}
  done

  echo "${sectors_list}"
}

# Callback of image_process_geometry. Format a partition by give offset,
# size (sectors), and index.
image_geometry_format_partition() {
  local offset="$1"
  local sectors="$2"
  local index="$3"
  local output_file="$4"
  local filesystem="$5"

  if [ "${offset}" = "0" ]; then
    # first entry is CGPT; ignore.
    return
  fi

  cgpt add -b "${offset}" -s "${sectors}" -i "${index}" -t "data" \
           -l "DATA" "${output_file}"

  part_dev=$(sudo losetup -f --show --offset="$((offset * IMAGE_CGPT_BS))" \
             --sizelimit="$((sectors * IMAGE_CGPT_BS))" "${output_file}")
  # Format the file.
  sudo "mkfs.${filesystem}" "${part_dev}" ||
    die "Failed to format file: ${output_file}."
  sudo losetup -d "${part_dev}"
}

# Create a cgpt image with partitions
# Usage: build_image_file <part_bytes_list> <output_file> <part_filesystem>
# Args:
#   part_bytes_list: a list of numbers specifying the size in bytes of
#       different partitions. For example: "10000000,400000000".
#   output_file: the output image file.
#   part_filesystem: filesystem format for each partition, ex: ext4, ntfs.
build_image_file() {
  local part_bytes_list="$1"
  local output_file="$2"
  local part_filesystem="$3"
  local sectors_list=$(bytes_to_sectors_list "${part_bytes_list}")

  image_geometry_build_file "${sectors_list}" "${output_file}"

  # Format each partition.
  image_process_geometry "${IMAGE_CGPT_START_SIZE} ${sectors_list}" \
                         image_geometry_format_partition \
                         "${output_file}" "${part_filesystem}"
}

# Usage: copy_dirs_to_partition <src_dir> <image_file> <part_num> <dst_dir>
# Args:
#   src_dir: the source directory to copy from.
#   image_file: The image file.
#   part_num: The partition of the image_file to store the source_dir.
#   dst_dir: the destination directory to copy to.
copy_dir_to_partition() {
  local src_dir="$1"
  local image_file="$2"
  local part_num="$3"
  local dst_dir="$4"
  local data_dir="$(mktemp -d)"

  alert "Copying ${src_dir} to partition #${part_num} of ${image_file}..."

  image_add_temp "${data_dir}"
  image_mount_partition "${image_file}" "${part_num}" "${data_dir}" "rw"
  # Add a trailing / on the source to "copy the contents of this directory"
  # as opposed to "copy the directory by name".
  sudo rsync -Pa "${src_dir}/" "${data_dir}/${dst_dir}"
  image_umount_partition "${data_dir}"
}

main() {
  local compressed_size

  if [ "$#" -lt 1 ]; then
    flags_help
    exit 1
  fi

  if [ -f "${FLAGS_output}" ] && [ "${FLAGS_force}" != "${FLAGS_TRUE}" ]; then
    die "Output file ${FLAGS_output} already exists." \
        "To overwrite the file, add --force."
  fi

  compressed_size=$(compress_partitions "${FLAGS_save_partitions}" "$@")
  build_image_file "${compressed_size}" "${FLAGS_output}" "${FLAGS_format}"
  copy_dir_to_partition "${INSTALLER_RESOURCES_DIR}" "${FLAGS_output}" \
                        "${DATA_PART_NUM}" "installer_resources"
}

set -e
trap on_exit EXIT
main "$@"
