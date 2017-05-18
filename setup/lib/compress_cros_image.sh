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

# Finds the best gzip compressor and invoke it
image_gzip_compress() {
  # -n (and -T for pigz) omits name/time from the header so that the
  # resultant files are deterministic and hashes do not change each
  # time.
  if image_has_command pigz; then
    # echo " ** Using parallel gzip **" >&2
    # Tested with -b 32, 64, 128(default), 256, 1024, 16384, and -b 32 (max
    # window size of Deflate) seems to be the best in output size.
    pigz -nT -b 32 "$@"
  else
    gzip -n "$@"
  fi
}

# Finds the best bzip2 compressor and invoke it
image_bzip2_compress() {
  if image_has_command pbzip2; then
    pbzip2 "$@"
  else
    bzip2 "$@"
  fi
}
