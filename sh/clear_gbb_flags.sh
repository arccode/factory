#!/bin/sh
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# This script clears the GBB header flags in system firmware
#

. "$(dirname "$0")/common.sh" || exit 1

if [ "$#" -gt "1" ]; then
  alert "ERROR: Usage: $0 [main_firmware]"
  exit 1
fi

_STDERR="$(mktemp --tmpdir)"
_STDOUT="$(mktemp --tmpdir)"
TMPFILE="$(mktemp --tmpdir)"
FIRMWARE_IMAGE="$([ -z "$1" ] || readlink -f "$1")"
RETRIES=2
FLASHROM_READ_PARAM="flashrom -p internal:bus=spi"
FLASHROM_WRITE_PARAM="flashrom -p internal:bus=spi --fast-verify"

cleanup() {
  rm -f "$_STDERR" "$_STDOUT" "$TMPFILE"
}

invoke() {
  # Usage: invoke "message" "shell-command"
  local result=0
  local message="$1"
  shift
  eval $@ >"$_STDOUT" 2>"$_STDERR" || result=$?
  if [ "$result" != 0 ]; then
    alert "ERROR: Failed to $message"
    alert "Command detail: $@"
    cat "$_STDOUT" "$_STDERR" 1>&2
    exit 1
  fi
  cat "$_STDOUT"
  return $result
}

clear_gbb_flags() {
  # Usage: clear_gbb_flags [main_firmware]
  local flags_info flags
  if [ -z "$FIRMWARE_IMAGE" ]; then
    FIRMWARE_IMAGE="$TMPFILE"
    invoke "Read GBB" "$FLASHROM_READ_PARAM -i GBB -r '$FIRMWARE_IMAGE'"
  fi

  flags_info="$(invoke "Flags" "gbb_utility -g --flags '$FIRMWARE_IMAGE'")" ||
    flags_info=""
  alert "flags_info: [$flags_info]"
  (echo "$flags_info" | grep -q "^flags: ") || flags_info=""
  if [ -z "$flags_info" ]; then
    echo "Failed to extract GBB header flags."
    exit 1
  fi
  flags="$(($(echo "$flags_info" | sed 's/^flags: //')))"
  if [ "$flags" = "0" ]; then
    alert "SUCCESS: Verification complete."
    exit 0
  elif [ "$RETRIES" -gt "1" ]; then
    # Try to update GBB flags
    alert "Clearing system GBB header flag..."
    invoke "Set Flags" "gbb_utility -s --flags=0 '$FIRMWARE_IMAGE' '$TMPFILE'"
    invoke "Write GBB" "$FLASHROM_WRITE_PARAM -i GBB -w '$TMPFILE'"
    rm -f "$TMPFILE"
    invoke "Read GBB" "$FLASHROM_READ_PARAM -i GBB -r '$TMPFILE'"
    alert "Re-try verification..."
    FIRMWARE_IMAGE="$TMPFILE"
  fi
}

set -e
trap cleanup EXIT
alert "Checking firmware GBB flags..."
while [ "$RETRIES" -gt 0 ]; do
  clear_gbb_flags "$FIRMWARE_IMAGE"
  RETRIES="$((RETRIES - 1))"
done
exit 1
