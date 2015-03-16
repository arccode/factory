#!/bin/sh
# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script restarts factory test program.

SCRIPT="$0"

. /usr/local/factory/sh/common.sh

# Restart without session ID, the parent process may be one of the
# processes we plan to kill.
if [ -z "$_DAEMONIZED" ]; then
  _DAEMONIZED=TRUE setsid "$SCRIPT" "$@"
  exit $?
fi

usage_help() {
  echo "usage: $SCRIPT [options]
    options:
      -s | state:   clear state files ($FACTORY_BASE/state)
      -l | log:     clear factory log files ($FACTORY_BASE/log)
      -t | tests:   clear test data ($FACTORY_BASE/tests)
      -r | run:     clear run data (/var/run/factory)
      -a | all:     clear all of the above
      -d | vpd:     clear VPD
      -h | help:    this help screen
      --automation-mode MODE:
                    set factory automation mode (none, partial, full);
                    default: none
      --no-auto-run-on-start:
                    do not automatically run test list when Goofy starts
  "
}

clear_files() {
  enabled="$1"
  dir="$2"
  [ -n "$enabled" ] && echo rm -rf "$FACTORY_BASE/$dir/*"
}

kill_tree() {
  local pid="$1"
  local sig="${2:-TERM}"
  kill -STOP ${pid}  # Stop parent from generating more children
  for child in $(ps -o pid --no-headers --ppid ${pid}); do
    kill_tree ${child} ${sig}
  done
  kill -${sig} ${pid} 2>/dev/null
}

clear_vpd=false
automation_mode=none
stop_auto_run_on_start=false
delete=""
while [ $# -gt 0 ]; do
  opt="$1"
  shift
  case "$opt" in
    -l | log )
      delete="$delete $FACTORY_BASE/log"
      ;;
    -s | state )
      delete="$delete $FACTORY_BASE/state"
      ;;
    -t | tests )
      delete="$delete $FACTORY_BASE/tests"
      ;;
    -r | run )
      delete="$delete /var/run/factory"
      ;;
    -a | all )
      delete="$delete $FACTORY_BASE/log $FACTORY_BASE/state"
      delete="$delete $FACTORY_BASE/tests /var/run/factory"
      ;;
    -d | vpd )
      clear_vpd=true
      ;;
    -h | help )
      usage_help
      exit 0
      ;;
    --automation-mode )
      case "$1" in
        none | partial | full )
          automation_mode="$1"
          shift
          ;;
        * )
          usage_help
          exit 1
          ;;
      esac
      ;;
    --no-auto-run-on-start )
      stop_auto_run_on_start=true
      ;;
    * )
      echo "Unknown option: $opt"
      usage_help
      exit 1
      ;;
  esac
done

goofy_control_pid="$(pgrep goofy_control)"
echo -n "Stopping factory test programs... "
kill_tree $goofy_control_pid
for sec in 3 2 1; do
  echo -n "${sec} "
  sleep 1
done
kill_tree $goofy_control_pid KILL
echo "done."

for d in $delete; do
  rm -rf "$d"
  mkdir -p "$d"
done

if $clear_vpd; then
  echo Clearing RO VPD...
  vpd -i RO_VPD -O
  echo Clearing RW VPD...
  vpd -i RW_VPD -O
fi

find ${FACTORY_BASE} -wholename "${AUTOMATION_MODE_TAG_FILE}" -delete
if [ "${automation_mode}" != "none" ]; then
  echo Enable factory test automation with mode: ${automation_mode}
  echo "${automation_mode}" > ${AUTOMATION_MODE_TAG_FILE}
  if ${stop_auto_run_on_start}; then
    touch ${STOP_AUTO_RUN_ON_START_TAG_FILE}
  else
    rm -f ${STOP_AUTO_RUN_ON_START_TAG_FILE}
  fi
fi

echo "Restarting factory tests..."
# Ensure full stop (instead of 'restart'), we don't want to have the same
# factory process recycled after we've been killing bits of it. Also because we
# need two jobs (factory and ui) both restarted.
#
# Add /sbin to PATH; that's usually where stop and start are, and
# /sbin may not be in the path.
export PATH=/sbin:"$PATH"
(status factory | grep -q 'stop/waiting') || stop factory
(status ui | grep -q 'stop/waiting') || stop ui
start factory
