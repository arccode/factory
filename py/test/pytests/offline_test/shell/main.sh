#!{%sh%}
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

DATA_DIR={%data_root%}
SCRIPT_DIR={%script_root%}
TOTAL_TASKS={%total_tasks%}
DELAY_AFTER_REBOOT={%delay_after_reboot%}
export CROS_FACTORY_DATA_DIR="${DATA_DIR}/root"
export LOGFILE="${DATA_DIR}/logfile"
export CROS_FACTORY_RUN_PATH="${DATA_DIR}/run"

. "${SCRIPT_DIR}/callback.sh"

log() {
  local prefix="$1"
  local date="$(date -u)"
  shift

  # Use awk to ensure each line of $* will have correct prefix.
  echo "$*" | toybox sed "s/^/[${date} ${prefix}] /" >&2
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
  error "$*"
  echo "FAILED" >"${DATA_DIR}/state"
  on_test_failed

  sync
  exit 1
}

delay_start() {
  # Delay a given time after device booted.
  local uptime=""
  # Only keep the first integer part.
  uptime="$(cat /proc/uptime | cut -f1 -d'.')"
  if [ "${DELAY_AFTER_REBOOT}" -gt "${uptime}" ]; then
    local diff="$((${DELAY_AFTER_REBOOT} - ${uptime}))"
    info "Wait for ${diff} second(s) to start."
    sleep "${diff}"
  fi
}

check_time() {
  local current_time="$(date -u '+%s')"
  local last_check_time="$(head -n 1 "${DATA_DIR}/last_check_time" || echo 0)"
  if [ "${last_check_time}" -gt "${current_time}" ]; then
    local old_time="$(date -u)"
    local last_check_time="$(tail -n 1 "${DATA_DIR}/last_check_time")"
    date -u "${last_check_time}"
    warn "go back in time, reset time to last checked time (was ${old_time})"
  fi

  # 1. save current time in a comparable format: seconds since epoch.
  date -u '+%s' >"${DATA_DIR}/last_check_time"
  # 2. save current time in the format used for setting date.
  date -u '+%m%d%H%M%Y.%S' >>"${DATA_DIR}/last_check_time"
}

all_test_passed() {
  info "All tests passed!"
  echo "$((${TOTAL_TASKS} + 1))" >"${DATA_DIR}/task_id"
  echo "PASSED" >"${DATA_DIR}/state"

  on_all_test_passed

  sync
}

main() {
  delay_start
  local next_task="$(cat ${DATA_DIR}/task_id || echo 1)"
  local state="$(cat ${DATA_DIR}/state || echo)"

  check_time

  if [ "${next_task}" -gt "${TOTAL_TASKS}" ]; then
    all_test_passed
    return 0
  fi

  if [ "${state}" = "running" ]; then
    if [ ! -e "${DATA_DIR}/should_reboot" ]; then
      if {%check_reboot%}; then
        die unexpected reboot
      else
        info "continue last test"
      fi
    fi
  elif [ "${state}" = "FAILED" ]; then
    on_test_failed
    exit 1
  fi

  local i
  for i in $(seq "${next_task}" "${TOTAL_TASKS}"); do
    check_time
    info "running task_${i}"
    echo "${i}" >"${DATA_DIR}/task_id"
    echo "running" >"${DATA_DIR}/state"
    rm -f "${DATA_DIR}/should_reboot"

    on_start_test

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
