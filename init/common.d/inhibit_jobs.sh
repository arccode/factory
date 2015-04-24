#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Install the job filter to inhibit Upstart jobs.
mount --bind "$(dirname $(readlink -f $0))/inhibit_jobs/filter.sh" \
  /usr/sbin/job-filter
