#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

INIT_DIR=/etc/init

if [ -z "$1" ]; then
  echo "Usage: $0 JOBNAME" >&2
  exit 1
fi

job_name=$1
job_path=${INIT_DIR}/${job_name}.conf

# Unmount the /dev/null that's covering the job
umount "$job_path"
initctl reload-configuration
initctl start "${job_name}"

# Cover it back up afterwards. It will keep running even when covered.
mount --bind /dev/null "$job_path"
initctl reload-configuration
