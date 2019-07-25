#!/bin/sh
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# In http://crbug.com/936818 and also http://crrev.com/c/1494694, /tmp is
# mounted as noexec by default, and we won't remount it to executable at
# test image anymore.
# This change break factory stuff and cause b/138982809. Also, it may break the
# factory tests, factory services..., etc. We would like to re-enabled it at
# factory environment.

main() {
  mount -n -o remount,exec,suid /tmp
}

main "$@"
