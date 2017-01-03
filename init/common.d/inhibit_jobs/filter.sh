#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This is a hook to /usr/sbin/job-filter, invoked by /etc/init/job-filter.conf.
# $1 is the name of job to be filtered.
#
# To start an inhibited job, run:
#  start job-filter JOB=<JOBNAME> disable_inhibit=1

# The job directory can't be fetched by using $(readlink -f $0) because this
# file will be re-mounted in /usr/sbin.
JOBS_DIR=/usr/local/factory/init/common.d/inhibit_jobs
JOB_NAME="$1"
JOB_FILE="${JOBS_DIR}/${JOB_NAME}"

if [ "${disable_inhibit}" = 1 ]; then
  start "${JOB_NAME}"
elif [ -e "${JOB_FILE}" ]; then
  stop -n "$1"
  if [ -x "${JOB_FILE}" ]; then
    "${JOB_FILE}"
  fi
fi
