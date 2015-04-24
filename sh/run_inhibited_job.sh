#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

if [ -z "$1" ]; then
  echo "Usage: $0 JOBNAME" >&2
  exit 1
fi

initctl start job-filter JOB="$1" disable_inhibit=1 >/dev/null 2>&1
initctl list | grep "$1"
