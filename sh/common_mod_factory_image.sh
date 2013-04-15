#!/bin/bash

# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

die() {
  echo "ERROR: $*"
  exit 1
}

if [ -z "${ROOT_FS_DIR}" ]; then
  die "ROOT_FS_DIR not defined. This script should only be used in build_image"
fi
echo "Unmerge redundant packages for factory image."
packages_to_unemerge=( binutils )
for package in "${packages_to_unemerge[@]}"; do
  echo "Unmerging ${package}"
  sudo ROOT="${ROOT_FS_DIR}/usr/local" emerge -Cq "${package}" ||
    die "Failed unmerging ${package}"
done
