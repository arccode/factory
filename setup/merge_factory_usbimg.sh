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
# 8-12 reserved for legacy paritions
#   13 kernel    [install-usbimg4]
#   14 rootfs    [install-usbimg4]
#   15 kernel    [install-usbimg5]
#   16 rootfs    [install-usbimg5]
#   ...
# --------------------------------
merge_images() {
  local output_file="$1"
  local image_file
  shift

  # Basically the output file should be sized in sum of all input files.
  info "Scanning input files..."
  local master_size="$(stat --format="%s" "$1")"
  local new_sectors=$((master_size / 512))
  : $((new_sectors -= $("${SCRIPT_DIR}/pygpt" show -i 1 -s "$1") ))
  for image_file in "$@"; do
    : $((new_sectors += $("${SCRIPT_DIR}/pygpt" show -i 1 -s "${image_file}") ))
  done
  local new_size_K="$((new_sectors / 2))"
  info "Creating a new image file in $((new_size_K / 1024))M..."
  cp -f "$1" "${output_file}"
  truncate -s "${new_size_K}K" "${output_file}"
  "${SCRIPT_DIR}/pygpt" repair --expand "${output_file}"

  local image all_payloads="$(mktemp -d)" stateful="$(mktemp -d)"
  image_add_temp "${all_payloads}"
  image_add_temp "${stateful}"

  image_mount_partition "${output_file}" 1 "${all_payloads}" "rw"
  mkdir -p "${all_payloads}/cros_payloads"
  for image_file in "$@"; do
    info "Collecting RMA payloads from ${image_file}..."
    image_mount_partition "${image_file}" 1 "${stateful}" "ro"
    cp -pr "${stateful}"/cros_payloads/* "${all_payloads}/cros_payloads/."
    image_umount_partition "${stateful}"
  done
  image_umount_partition "${all_payloads}"

  local temp_master="${output_file}.wip"
  mv -f "${output_file}" "${temp_master}"
  image_add_temp "${temp_master}"

  local builder="${SCRIPT_DIR}/make_universal_factory_shim.sh"
  "${builder}" -m "${temp_master}" -f "${output_file}" "$@"
}

main() {
  local force=""
  local output=""

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

  output="$1"
  shift
  if [ -f "$output" -a -z "$force" ]; then
    die "Output file $output already exists. To overwrite the file, add -f."
  fi
  [ -z "$force" ] || rm -f "$output"

  # Reset trap here to check whether output file is generated or not.
  # Use double quote to expand the local variable ${output} now.
  trap "check_output_on_exit ${output}" EXIT
  merge_images "$output" "$@"
}

set -e
trap on_exit EXIT
main "$@"
