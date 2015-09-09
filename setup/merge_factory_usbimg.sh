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
# A typical layout of an USB disk image:
# ---------------------
#  1 stateful
#  2 kernel   [install]
#  3 rootfs   [install]
#  4 kernel   [factory]
#  5 rootfs   [factory]
#  6 kernel   [release]
#  7 rootfs   [release]
#  8 oem
# 12 efi
# ---------------------
#
# This function extracts partitions 1, 4-8 and 12 from each input image
# and put them into a resource file. Then invoke make_universal_factory_shim.sh
# to generate the output image by merging the resource file to partition 1 and
# merging partition 2/3 of each input image.
#
# The layout of the merged output image:
# --------------------------------
#    1 resource  [Partitions 1, 4-8, 12 of each usbimgX]
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
  shift

  local compressor="$SCRIPT_DIR/make_image_resource.sh"
  local builder="$SCRIPT_DIR/make_universal_factory_shim.sh"
  local save_partitions="1,4,5,6,7,8,12"

  "$compressor" --force --save_partitions="$save_partitions" \
                --output "$RESOURCE_FILE" "$@"
  "$builder" -m "$RESOURCE_FILE" -f "$output_file" "$@"
}

# lsb file is required for factory shim bootstrapping.
generate_lsb() {
  local image_file="$1"
  local temp_mount="$(mktemp -d)"
  local lsb_file="${temp_mount}/dev_image/etc/lsb-factory"

  image_add_temp "${temp_mount}"
  image_mount_partition "${image_file}" "1" "${temp_mount}" "rw" ||
    die "Failed to mount partition 1 in ${image_file}"

  # INSTALL_FROM_USB=1 tells factory_installer/factory_install.sh to install
  # images from USB drive instead of mini-omaha server.
  # Install shim kernel and rootfs are in partition #2 and #3 in a usbimg,
  # and the factory and release image partitions are moved to +2 location.
  # USB_OFFSET=2 tells factory_installer/factory_install.sh this information.
  sudo mkdir -p "$(dirname "${lsb_file}")"
  (echo "FACTORY_INSTALL_FROM_USB=1" &&
    echo "FACTORY_INSTALL_USB_OFFSET=2") |
    sudo dd of="${lsb_file}"

  image_umount_partition "${temp_mount}"
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
  generate_lsb "$output"
}

set -e
trap on_exit EXIT
main "$@"
