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
      -r | run:     clear run data (/var/run/factory)
      -a | all:     clear all of the above
      -d | vpd:     clear VPD
      -h | help:    this help screen
  "
}

clear_files() {
  enabled="$1"
  dir="$2"
  [ -n "$enabled" ] && echo rm -rf "$FACTORY_BASE/$dir/*"
}

clear_vpd=false
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
  rm -rf "$d"
  mkdir -p "$d"
done

if $clear_vpd; then
  echo Clearing RO VPD...
  vpd -i RO_VPD -O
  echo Clearing RW VPD...
  vpd -i RW_VPD -O
fi

echo "Restarting factory tests..."
# Ensure full stop, we don't want to have the same factory
# process recycled after we've been killing bits of it.
#
# Add /sbin to PATH; that's usually where stop and start are, and
# /sbin may not be in the path.
export PATH=/sbin:"$PATH"
stop factory
start factory
