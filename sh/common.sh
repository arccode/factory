# Copyright 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Common library for Google Factory Tools shell scripts.

# ======================================================================
# global variables

# base factory state and log directory
FACTORY_BASE="/var/factory"

# base factory init directory
FACTORY_INIT_BASE="/usr/local/factory/init"

# ======================================================================
# message and error handling

# usage: alert messages...
alert() {
  echo "$*" 1>&2
}

# usage: die messages...
die() {
  alert "ERROR: $*"
  exit 1
}
