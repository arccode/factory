#!/bin/sh
# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script restarts factory test program.

FACTORY_BASE=/var/factory
SCRIPT="$0"

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
      -a | all:     clear everything
      -h | help:    this help screen
  "
}

clear_files() {
  enabled="$1"
  dir="$2"
  [ -n "$enabled" ] && echo rm -rf "$FACTORY_BASE/$dir/*"
}

delete=""
while [ $# -gt 0 ]; do
  opt="$1"
  shift
  case "$opt" in
    -l | log )
      delete="$delete log"
      ;;
    -s | state )
      delete="$delete state"
      ;;
    -t | tests )
      delete="$delete tests"
      ;;
    -a | all )
      delete="$delete log state tests"
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

echo -n "Stopping factory test programs... "
(pkill python; pkill X; killall /usr/bin/python) 2>/dev/null
for sec in 3 2 1; do
  echo -n "${sec} "
  sleep 1
done
killall -9 /usr/bin/python 2>/dev/null
echo "done."

for d in $delete; do
  rm -rf /var/factory/$d
  mkdir -p /var/factory/$d
done

echo "Restarting factory tests..."
# Ensure full stop, we don't want to have the same factory
# process recycled after we've been killing bits of it.
stop factory
start factory
