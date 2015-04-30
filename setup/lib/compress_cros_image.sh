#!/bin/bash

# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script contains common utility functions to deal with Chromium OS
# images compression, especially for being redistributed into platforms
# without completed Chromium OS developing environment.

# Compresses kernel and rootfs of an imge file, and output its hash.
# Usage: compress_and_hash_memento_image kernel rootfs output_file
# Please see "mk_memento_images --help" for detail of parameter syntax
compress_and_hash_memento_image() {
  local kernel="$1"
  local rootfs="$2"
  local output_file="$3"
  [ "$#" = "3" ] || die "Internal error: compress_and_hash_memento_image $*"

  "${SCRIPT_DIR}/mk_memento_images.sh" \
      "${kernel}" "${rootfs}" "${output_file}" |
    grep hash |
    awk '{print $4}'
}

compress_and_hash_file() {
  local input_file="$1"
  local output_file="$2"

  if [ -z "${input_file}" ]; then
    # Runs as a pipe processor
    image_gzip_compress -c -9 |
    tee "${output_file}" |
    openssl sha1 -binary |
    openssl base64
  else
    image_gzip_compress -c -9 "${input_file}" |
    tee "${output_file}" |
    openssl sha1 -binary |
    openssl base64
  fi
}

compress_and_hash_partition() {
  local input_file="$1"
  local part_num="$2"
  local output_file="$3"

  image_dump_partition "${input_file}" "${part_num}" |
    compress_and_hash_file "" "${output_file}"
}

