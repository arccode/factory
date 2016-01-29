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
  local last_check_time="$(head -n 1 "${DATA_DIR}/last_check_time" || echo 0)"
  if [ "${last_check_time}" -gt "${current_time}" ]; then
    local old_time="$(date)"
    local last_check_time="$(tail -n 1 "${DATA_DIR}/last_check_time")"
    date "${last_check_time}"
    warn "go back in time, reset time to last checked time (was ${old_time})"
  fi

  # 1. save current time in a comparable format: seconds since epoch.
  date '+%s' >"${DATA_DIR}/last_check_time"
  # 2. save current time in the format used for setting date.
  date '+%m%d%H%M%Y.%S' >>"${DATA_DIR}/last_check_time"
}

all_test_passed() {
  info "All tests passed!"
  echo "$((${TOTAL_TASKS} + 1))" >"${DATA_DIR}/task_id"

  # TODO(stimim): call hooked function on finished
}

main() {
  local next_task="$(cat ${DATA_DIR}/task_id || echo 1)"
  local state="$(cat ${DATA_DIR}/state || echo)"

  check_time

  if [ "${next_task}" -gt "${TOTAL_TASKS}" ]; then
    all_test_passed
    return 0
  fi

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

  all_test_passed
  return 0
}

# tasks start here
{%tasks%}
# end tasks

main
