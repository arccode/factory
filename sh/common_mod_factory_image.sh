#!/bin/bash

# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

die() {
  echo "ERROR: $*"
  exit 1
}

if [[ $# -ne 1 ]]; then
  die "Usage: $0 root_fs_dir"
fi
root_fs_dir=$1
echo "Unmerge redundant packages for factory image."
packages_to_unemerge=( binutils )
for package in "${packages_to_unemerge[@]}"; do
  echo "Unmerging ${package}"
  sudo ROOT="${root_fs_dir}/usr/local" emerge -Cq "${package}" ||
    die "Failed unmerging ${package}"
done
