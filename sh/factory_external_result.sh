#!/bin/sh
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 NAME RESULT" 2>&1
  exit 1
fi
RUN_FACTORY_EXTERNAL_DIR=/run/factory/external
NAME="$1"
shift

set -e
mkdir -p "${RUN_FACTORY_EXTERNAL_DIR}"
echo "$@" >"${RUN_FACTORY_EXTERNAL_DIR}/${NAME}"
