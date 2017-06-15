#!/bin/sh

# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Script to merge multiple USB installation disk images.

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
. "$SCRIPT_DIR/factory_common.sh" || exit 1

# Temp file to store image resources.
RESOURCE_FILE="$(mktemp)"

alert() {
  echo "$*" >&2
}

die() {
  alert "ERROR: $*"
  exit 1
}

check_output_on_exit() {
  local output_file="$1"

  if [ ! -f "$output_file" ]; then
    alert "Failed to generate the output file: $output_file."
    alert "This may be related to not enough space left on /tmp."
    alert "Please try to specify TMPDIR to another location."
    alert "For example, TMPDIR=/some/other/dir $0"
  fi
  on_exit
}

on_exit() {
  rm -f "$RESOURCE_FILE"
  image_clean_temp
}

usage_die() {
  alert "Usage: $SCRIPT [-f] output usbimg1 [usbimg2 usbimg3 ...]"
  exit 1
}

# Clones the partition GPT info (type, attr, label).
clone_partition_type() {
  local input_file="$1" input_part="$2" output_file="$3" output_part="$4"

  local part_type="$("${CGPT}" show -q -n -t -i "$input_part" "$input_file")"
  local part_attr="$("${CGPT}" show -q -n -A -i "$input_part" "$input_file")"
  local part_label="$("${CGPT}" show -q -n -l -i "$input_part" "$input_file")"

  "${CGPT}" add -t "${part_type}" -l "${part_label}" -A "${part_attr}" \
    -i "${output_part}" "${output_file}"
}

# Merge multiple USB installation disk images.
#
# The usbimg should have factory_install kernel and rootfs in (2, 3) and
# resources in stateful partition cros_payloads.
# This function extracts merges all stateful partitions and invoke
# make_universal_factory_shim.sh to generate the output image by merging the
# resource file to partition 1 and merging partition 2/3 of each input image.
#
# The layout of the merged output image:
# --------------------------------
#    1 stateful  [cros_payloads from all usbimgX]
#    2 kernel    [install-usbimg1]
#    3 rootfs    [install-usbimg1]
#    4 kernel    [install-usbimg2]
#    5 rootfs    [install-usbimg2]
#    6 kernel    [install-usbimg3]
#    7 rootfs    [install-usbimg3]
#   ...
# --------------------------------
merge_images() {
  local output_file="$1"
  local image
  local pygpt="${SCRIPT_DIR}/pygpt"
  shift

  # Basically the output file should be sized in sum of all input files.
  info "Scanning input files..."
  local sectors_list=""
  local new_sectors=0
  for image_file in "$@"; do
    : $((new_sectors += $("${pygpt}" show -i 1 -s "${image_file}") ))
    sectors_list="${sectors_list} $("${pygpt}" show -i 2 -s "${image_file}")"
    sectors_list="${sectors_list} $("${pygpt}" show -i 3 -s "${image_file}")"
  done

  # Put new stateful partition in first (partition 1).
  sectors_list="${new_sectors} ${sectors_list}"
  image_geometry_build_file "${sectors_list}" "${output_file}"
  local new_size="$(stat --format="%s" "${output_file}")"
  info "Creating new image file in $((new_size / 1048576))M..."

  # Clone and resize stateful partition.
  clone_partition_type "$1" 1 "${output_file}" 1
  image_partition_overwrite "${image_file}" "1" "${output_file}" "1"
  local state_dev="$(image_map_partition "${output_file}" 1)"
  sudo e2fsck -f "${state_dev}"
  sudo resize2fs "${state_dev}"
  image_unmap_partition "${state_dev}"

  # Clone root and kernel partitions
  local index=2
  for image_file in "$@"; do
    info "Copying kernel and rootfs from ${image_file}..."
    clone_partition_type "${image_file}" "2" "${output_file}" "${index}"
    image_partition_copy "${image_file}" "2" "${output_file}" "${index}"
    : $((index += 1))
    clone_partition_type "${image_file}" "3" "${output_file}" "${index}"
    image_partition_copy "${image_file}" "3" "${output_file}" "${index}"
    : $((index += 1))
  done

  local all_payloads="$(mktemp -d)" stateful="$(mktemp -d)"
  image_add_temp "${all_payloads}"
  image_add_temp "${stateful}"

  image_mount_partition "${output_file}" 1 "${all_payloads}" "rw"
  sudo mkdir -p "${all_payloads}/cros_payloads"

  # This must be the last loop on $@.
  # $@ is changed since here because stateful partition in first image is
  # already copied.
  shift
  for image_file in "$@"; do
    info "Collecting RMA payloads from ${image_file}..."
    image_mount_partition "${image_file}" 1 "${stateful}" "ro"
    sudo cp -pr "${stateful}"/cros_payloads/* "${all_payloads}/cros_payloads/."
    image_umount_partition "${stateful}"
  done
  image_umount_partition "${all_payloads}"

  info "Merged new image created successfully: ${output_file}."
}

main() {
  local force=""
  local output=""

  umask 022

  while [ "$#" -gt 1 ]; do
    case "$1" in
      "-f" )
        force="True"
        shift
        ;;
      * )
        break
    esac
  done

  if [ "$#" -lt 2 ]; then
    alert "ERROR: invalid number of parameters ($#)."
    usage_die
  fi

  # Check required tools.
  # TODO(hungte) Change this to Python when we have implemented 'add' in pygpt.
  if [ -z "${CGPT}" ]; then
    die "Missing cgpt. Please install cgpt or run inside chroot."
  fi

  output="$1"
  shift
  if [ -f "$output" -a -z "$force" ]; then
    die "Output file $output already exists. To overwrite the file, add -f."
  fi
  [ -z "$force" ] || rm -f "$output"

  # Reset trap here to check whether output file is generated or not.
  # Use double quote to expand the local variable ${output} now.
  # shellcheck disable=SC2064
  trap "check_output_on_exit ${output}" EXIT
  merge_images "$output" "$@"
}

set -e
trap on_exit EXIT
main "$@"
