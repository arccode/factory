#!/bin/sh
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script converts a Chromium OS (test) image into Docker image.

# These global variables must be cleaned up on exit.
LOOP=""
TMPROOT=""

die () {
  trap - EXIT
  echo "ERROR: $*"
  cleanup
  exit 1
}

cleanup() {
  if [ -d "${TMPROOT}" ]; then
    sudo umount -R "${TMPROOT}"/*
    sudo rm -rf "${TMPROOT}"
    TMPROOT=""
  fi
  if [ -n "${LOOP}" ]; then
    sudo losetup -d "${LOOP}"
    LOOP=""
  fi
}

unknown_failure() {
  die "ERROR: Unexpected error. Aborted."
}

get_lsb_value() {
  sed -n "s/^$1=//p" "$2/etc/lsb-release"
}

main() {
  set -e
  trap unknown_failure EXIT

  if [ "$#" != 1 ]; then
    die "Usage: $0 PATH_TO/chromiumos_test_image.bin"
  fi

  local image="$1"
  if [ ! -f "${image}" ]; then
    die "Cannot find image file: ${image}"
  fi

  LOOP="$(sudo losetup -P --show --find "${image}")"

  if [ ! -b "${LOOP}p3" ]; then
    die "Failed to mount Chromium OS image file: ${image}"
  fi

  echo "Mounting image file: ${image}"
  TMPROOT="$(mktemp -d)"
  local root="${TMPROOT}/root"
  local state="${TMPROOT}/state"
  mkdir "${root}" "${state}"
  sudo mount -t ext2 -o ro "${LOOP}p3" "${root}"
  sudo mount -o ro "${LOOP}p1" "${state}"
  sudo mount --bind "${state}/var_overlay" "${root}/var"
  sudo mount --bind "${state}/dev_image" "${root}/usr/local"

  echo "Checking image board and version..."
  local board="$(get_lsb_value CHROMEOS_RELEASE_BOARD "${root}")"
  local version="$(get_lsb_value CHROMEOS_RELEASE_VERSION "${root}")"
  : version="${version%% *}"
  if [ -z "${board}" ]; then
    die "Not a valid image file (missing CHROMEOS_RELEASE_BOARD): ${image}"
  fi
  if [ -z "${version}" ]; then
    die "Not a valid image file (missing CHROMEOS_RELEASE_VERSION): ${image}"
  fi

  local pv="pv"
  if ! type pv >/dev/null 2>&1; then
    pv="cat"
  fi

  local docker_name="cros/${board}_test:${version}"
  echo "Creating Docker image as ${docker_name} ..."
  sudo tar -C "${root}" -c . | "${pv}" | docker import - "${docker_name}"
  sudo docker tag "${docker_name}" "cros/${board}_test:latest"

  trap cleanup EXIT
  echo "Successfully built docker image [${docker_name}] from ${image}."
}
main "$@"
