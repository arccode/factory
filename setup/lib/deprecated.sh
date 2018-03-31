#!/bin/sh
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

script="$(basename "$0")"
script_dir="$(dirname "$0")"
name="${script%%.*}"

new_args="$@"
case "${name}" in
  mount_partition)
    name='mount'
    ;;
esac

echo "This script is deprecated. Please run 'image_tool' instead:

  ${script_dir}/image_tool ${name} $(echo ${new_args})"
exit 1
