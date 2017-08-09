#!/bin/sh
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This file will be executed when user logins into VT2 or ssh.

main() {
  # Put '/usr/local/factory/bin' at the head of PATH so that we can run factory
  # binaries easily.
  export PATH="/usr/local/factory/bin:${PATH}"
}

main "$@"
