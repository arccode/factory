#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

DATA_DIR={%data_root%}
TOTAL_TASKS={%total_tasks%}

log() {
  local prefix="$1"
  local date="$(date)"  # it turns out that strftime is not supported by all awk
  shift

  # Use awk to ensure each line of $* will have correct prefix.
  echo "$*" | awk "{print \"[${date} ${prefix}]\", \$0}" >&2
}

info() {
  log INFO "$*"
}

warn() {
  log WARN "$*"
}

error() {
  log ERROR "$*"
}

die() {
  # TODO(stimim): call hooked function on die
  error "$*"
  exit 1
}

check_time() {
  local current_time="$(date '+%s')"
  local last_check_time="$(cat ${DATA_DIR}/last_check_time || echo 0)"
  if [ "${last_check_time}" -gt "${current_time}" ]; then
    local old_time="$(date)"
    date "--date=@$((${last_check_time} + 1))"
    warn "go back in time, reset time to last checked time (was ${old_time})"
  fi

  date '+%s' >"${DATA_DIR}/last_check_time"
}

main() {
  local next_task="$(cat ${DATA_DIR}/task_id || echo 1)"
  local state="$(cat ${DATA_DIR}/state || echo)"

  check_time

  if [ "${state}" = "running" ]; then
    if [ ! -e "${DATA_DIR}/should_reboot" ]; then
      die unepected reboot
    fi
  fi

  local i
  for i in $(seq "${next_task}" "${TOTAL_TASKS}"); do
    check_time
    info "running task_${i}"
    echo "${i}" >"${DATA_DIR}/task_id"
    echo "running" >"${DATA_DIR}/state"
    rm -f "${DATA_DIR}/should_reboot"

    if "task_${i}" ; then
      info "task_${i}" PASSED
    else
      die "task_${i}" FAILED
    fi
  done

  info "All tests passed!"
  # TODO(stimim): call hooked function on finished
}

# tasks start here
{%tasks%}
# end tasks

main
