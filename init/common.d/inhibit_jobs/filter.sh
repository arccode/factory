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

if [ "${disable_inhibit}" = 1 ]; then
  start "$1"
elif [ -e "${JOBS_DIR}/$1" ]; then
  stop -n "$1"
fi
