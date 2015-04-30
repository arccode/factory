#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script performs following tasks to prepare a wiping process at reboot:
# - install "wiping" message and tag file
# - enable release partition
# - rollback if anything goes wrong
# To assign additional wiping tags, use FACTORY_WIPE_TAGS envinronment variable.
# Ex: FACTORY_WIPE_TAGS="fast" prepare_wipe.sh /dev/sda5

. "$(dirname "$0")/common.sh" || exit 1
set -e

# Variables for cleaning up
NEED_ROLLBACK=""

# Location for message and tag files
SCRIPT_DIR="$(dirname "$0")"
STATEFUL_PARTITION="/mnt/stateful_partition"
WIPE_TAG_FILE="$STATEFUL_PARTITION/factory_install_reset"
MESSAGE_FILE="$STATEFUL_PARTITION/wipe_message.txt"
MESSAGE_SOURCE="$SCRIPT_DIR/../misc/wipe_message.txt"
TAGS="factory"

rollback_changes() {
  # don't stop, even if we encounter any issues
  local failure_msg="WARNING: Failed to rollback some changes..."
  alert "WARNING: Rolling back changes."
  rm -f "$WIPE_TAG_FILE" 2>/dev/null || alert "$failure_msg"
}

cleanup() {
  if [ -n "$NEED_ROLLBACK" ]; then
    rollback_changes
  fi
}

install_message() {
  if [ ! -f "$MESSAGE_SOURCE" ]; then
    die "Missing message file for wiping: $MESSAGE_SOURCE"
  fi
  cp -f "$MESSAGE_SOURCE" "$MESSAGE_FILE" ||
    die "Failed to install message file: $MESSAGE_SOURCE => $MESSAGE_FILE"
  alert "Message file $MESSAGE_FILE installed."
}

install_wipe_tag() {
  # FACTORY_WIPE_TAGS is an environment variable.
  if [ -n "$FACTORY_WIPE_TAGS" ]; then
    TAGS="$TAGS $FACTORY_WIPE_TAGS"
  fi
  echo "$TAGS" >"$WIPE_TAG_FILE" ||
    die "Failed to create tag file: $WIPE_TAG_FILE"
  alert "Tag file $WIPE_TAG_FILE created: [$TAGS]."
}

main() {
  if [ "$#" != "1" ]; then
    alert "Usage: [FACTORY_WIPE_TAGS=fast] $0 release_rootfs"
    exit 1
  fi

  NEED_ROLLBACK="YES"
  install_message
  install_wipe_tag
  . "$SCRIPT_DIR/enable_release_partition.sh" "$1" || exit 1
  NEED_ROLLBACK=""
  alert "Prepare wipe: Complete."
}

trap cleanup EXIT
main "$@"
