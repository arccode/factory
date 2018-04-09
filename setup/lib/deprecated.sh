#!/bin/sh
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

script="$(basename "$0")"
script_dir="$(dirname "$0")"
name="${script%%.*}"

has() {
  local pattern="$1" var
  shift
  for var in "$@"; do
    if [ "${var}" = "${pattern}" ]; then
      return 0
    fi
  done
  return 1
}

replace() {
  local pattern="$1" var
  local repl="$2"
  shift
  shift
  for var in "$@"; do
    if [ "${var}" = "${pattern}" ]; then
      echo "${repl}"
      continue
    fi
    echo "${var}"
  done
}

new_args="$@"
case "${name}" in
  mount_partition)
    name='mount'
    ;;
  extract_firmware_updater)
    name='get_firmware'
    ;;
  netboot_firmware_settings)
    name='netboot'
    ;;
  resize_image_fs)
    name='resize'
    ;;
  make_docker_image)
    name='docker'
    ;;
  make_factory_package)
    if has "--diskimg" "$@"; then
      name='preflash'
      new_args="$(replace --diskimg -o "$@")"
    elif has "--usbimg" "$@"; then
      name='rma'
      new_args="$(replace --usbimg -o "$@")"
    fi
    ;;
esac

echo "This script is deprecated. Please run 'image_tool' instead:

  ${script_dir}/image_tool ${name} $(echo ${new_args})"
exit 1
