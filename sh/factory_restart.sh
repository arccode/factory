#!/bin/bash
# Copyright 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script restarts factory test program.

SCRIPT="$0"

. "$(dirname "$(readlink -f "${SCRIPT}")")"/common.sh

# Restart without session ID, the parent process may be one of the
# processes we plan to kill.
if [ -z "$_DAEMONIZED" ]; then
  _DAEMONIZED=TRUE setsid "$SCRIPT" "$@"
  exit $?
fi

# Add /sbin to PATH; that's usually where stop and start are, and
# /sbin may not be in the path.
PATH=/sbin:"$PATH"

usage_help() {
  echo "usage: $SCRIPT [options]
    options:
      -s | state:   clear state files ($FACTORY_BASE/state)
      -l | log:     clear factory log files ($FACTORY_BASE/log)
      -t | tests:   clear test data ($FACTORY_BASE/tests)
      -r | run:     clear run data (/run/factory)
      -a | all:     clear all of the above data
      -S | stop:    only stop the service, don't respawn
      -d | vpd:     clear VPD
      -c | chrome:  restart Chrome (UI)
      -h | help:    this help screen
  "
}

kill_tree() {
  local signal="${1:-TERM}"
  local pid
  shift

  # $* may contain spaces so we cannot quote it.
  # shellcheck disable=SC2048
  for pid in $*; do
    printf "%s " "${pid}"
    # ps output may contain leading space so we have to unquote it.
    kill_tree "${signal}" "$(ps -o pid --no-headers --ppid "${pid}")"
    kill "-${signal}" "${pid}" 2>/dev/null
  done
}

clear_vpd() {
  local region

  for region in "$@"; do
    echo "Clearing ${region} VPD region..."
    vpd -i "${region}_VPD" -O
  done
}

clear_data() {
  local data
  if [ $# -eq 0 ] ; then
    return
  fi

  echo "Clear data: $*"
  for data in "$@"; do
    rm -rf "${data}"
    mkdir -p "${data}"
  done
}

stop_services() {
  local service
  # Ensure full stop (instead of 'restart'), we don't want to have the same
  # factory process recycled after we've been killing bits of it. Also because we
  # need two jobs (factory and ui) both restarted.

  for service in "$@"; do
    (status "${service}" | grep -q 'stop/waiting') || stop "${service}"
  done
}

stop_session() {
  local goofy_control_pid
  goofy_control_pid="$(pgrep goofy_control)"

  printf "Attempt to stop gracefully... "
  # save pids in case their parents die and they are orphaned
  local all_pids
  all_pids="$(kill_tree TERM "${goofy_control_pid}")"

  local sec
  for sec in 3 2 1; do
    printf "%s " "${sec}"
    sleep 1
  done

  printf "Stopping factory test programs... "
  # all_pids must be passed as individual parameters so we should not quote it.
  kill_tree KILL "${all_pids}" > /dev/null
  echo "done."
}

main() {
  local data=()
  local vpd=()
  local services=("factory")
  local restart_factory=true
  local chrome_url="http://localhost:4012"

  while [ $# -gt 0 ]; do
    opt="$1"
    shift
    case "${opt}" in
      -l | log )
        data+=("${FACTORY_BASE}/log")
        ;;
      -S | stop )
        restart_factory=false
        chrome_url=""
        ;;
      -s | state )
        data+=("${FACTORY_BASE}/state")
        ;;
      -t | tests )
        data+=("${FACTORY_BASE}/tests")
        ;;
      -r | run )
        data+=("/run/factory")
        ;;
      -a | all )
        data+=("${FACTORY_BASE}/log" "${FACTORY_BASE}/state"
        "${FACTORY_BASE}/tests" "/run/factory")
        ;;
      -c | chrome )
        chrome_url=""
        services+=("ui")
        ;;
      -d | vpd )
        vpd+=("RO" "RW")
        ;;
      -h | help )
        usage_help
        exit 0
        ;;
      * )
        echo "Unknown option: $opt"
        usage_help
        exit 1
        ;;
    esac
  done

  if [ -n "${chrome_url}" ]; then
    chrome_openurl "${chrome_url}/restarting.html"
  fi

  stop_session
  stop_services "${services[@]}"
  clear_data "${data[@]}"
  clear_vpd "${vpd[@]}"

  # 'factory' service will also start 'ui' services internally, but if we don't
  # want to restart 'factory', we need to start 'ui' services by ourselves.
  local restart_services=()
  if [[ "${restart_factory}" == "true" ]]; then
    restart_services+=("factory")
  else
    # restart the services other than 'factory'
    restart_services+=("${services[@]}")
    for i in "${!restart_services[@]}"; do
      if [[ "${restart_services[i]}" == "factory" ]]; then
        unset 'restart_services[i]'
      fi
    done
  fi

  if (( "${#restart_services[@]}" )); then
    echo "Restarting" "${restart_services[@]}" "services..."
    start "${restart_services[@]}"
  fi
}
main "$@"
