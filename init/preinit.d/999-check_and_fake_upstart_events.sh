#!/bin/sh
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

fake_stopped_event_if_job_not_found () {
  # In upstart, "start on stopped xxx" means it is waiting
  # the event "stopped" with some variable contain value "xxx". When the "xxx"
  # job finished, the upstart will send out "stopped" event with an variable
  # pair "JOB=xxx".  However, crbug/818032 forbid passing the custom value with
  # upstart reserved key for seucrity reason. We use an arbitrary key to bypass
  # the restriction.

  local job_name="$1"

  if [ ! -f "/etc/init/${job_name}.conf" ]; then
    initctl emit --no-wait stopped "A=${job_name}"
  fi
}

main() {
  # Because some upstart jobs may not exist on some platform, the next stage of
  # upstart job will still wait them to finish. We need to fake the finished
  # event in upstart.

  fake_stopped_event_if_job_not_found boot-splash
}

main
