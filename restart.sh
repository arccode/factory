#!/bin/sh
# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script restarts factory test program.

FACTORY_LOG_FILE=/var/log/factory.log
FACTORY_START_TAG_FILE=/usr/local/autotest/factory_started
FACTORY_CONTROL_FILE=/usr/local/autotest/control
FACTORY_STATE_PREFIX=/var/log/factory_state

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
      -s | state:   clear state files, implies -r ( $FACTORY_STATE_PREFIX* )
      -l | log:     backup and reset factory log files ( $FACTORY_LOG_FILE )
      -c | control: refresh control file, implies -r ( $FACTORY_CONTROL_FILE )
      -r | restart: clear factory start tag ( $FACTORY_START_TAG_FILE )
      -a | all:     restart everything
      -h | help:    this help screen
  "
}

clear_files() {
  local opt="$1"
  local file="$2"
  local is_multi="$3"
  if [ -z "$opt" ]; then
    return 0
  fi
  if [ -n "$is_multi" ]; then
    echo -n "$file"* " "
    rm -rf "$file"*  2>/dev/null
  else
    echo -n "$file "
    rm -rf "$file" "$file.bak" 2>/dev/null
  fi
}

while [ $# -gt 0 ]; do
  opt="$1"
  shift
  case "$opt" in
    -l | log )
      opt_log=1
      ;;
    -s | state )
      opt_state=1
      opt_start_tag=1
      ;;
    -c | control )
      opt_control=1
      opt_start_tag=1
      ;;
    -r | restart )
      opt_start_tag=1
      ;;
    -a | all )
      opt_log=1
      opt_state=1
      opt_control=1
      opt_start_tag=1
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

echo -n "Resetting files: "
clear_files "$opt_log" "$FACTORY_LOG_FILE" ""
clear_files "$opt_state" "$FACTORY_STATE_PREFIX" "1"
clear_files "$opt_control" "$FACTORY_CONTROL_FILE" ""
clear_files "$opt_start_tag" "$FACTORY_START_TAG_FILE" ""
echo " done."

echo "Restarting new factory test program..."
# Ensure full stop, we don't want to have the same factory
# process recycled after we've been killing bits of it.
stop factory
start factory
