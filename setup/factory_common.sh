#!/bin/sh

# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Common script utilities loader for factor scripts

SCRIPT="$(readlink -f "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT")"

# Loads script libraries.
. "$SCRIPT_DIR/lib/shflags" || exit 1
. "$SCRIPT_DIR/lib/cros_image_common.sh" || exit 1
. "$SCRIPT_DIR/lib/compress_cros_image.sh" || exit 1
. "$SCRIPT_DIR/lib/chromeos-common.sh" || exit 1

# Finds binary utilities if available.
image_find_tool "cgpt" "$SCRIPT_DIR/bin"
image_find_tool "cgpt" "$SCRIPT_DIR/lib"

# Redirects tput to stderr, and drop any error messages.
tput2() {
  tput "$@" 1>&2 2>/dev/null || true
}

error() {
  tput2 bold && tput2 setaf 1
  echo "ERROR: $*" >&2
  tput2 sgr0
}


info() {
  tput2 bold && tput2 setaf 2
  echo "INFO: $*" >&2
  tput2 sgr0
}

warn() {
  tput2 bold && tput2 setaf 3
  echo "WARNING: $*" >&2
  tput2 sgr0
}

die() {
  [ -z "$*" ] || error "$@"
  exit 1
}
