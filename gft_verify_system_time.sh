#!/bin/sh
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script verifies that system time is later than filesystem creation time.

. "$(dirname "$0")/common.sh" || exit 1
set -e

verify_system_time() {
  local rootdev="$1"
  local label="Filesystem created: "

  local fs_creation_time="$(dumpe2fs -h "$rootdev" 2>/dev/null | grep "$label")"
  fs_creation_time="$(date -d "${fs_creation_time#"$label"}" "+%s")"
  local system_time="$(date "+%s")"
  if [ "$system_time" -lt "$fs_creation_time" ]; then
    die "System time ($system_time) earlier than filesystem creation time" \
        "($fs_creation_time)."
  fi
}

if [ "$#" != "1" ]; then
  die "Usage: $0 root_dev"
fi
verify_system_time "$@"
