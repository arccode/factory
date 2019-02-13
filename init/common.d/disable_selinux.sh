#!/bin/sh
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# We use "mount --bind" to stub "minijail0", this might break selinux policy
# for some programs.  (SELinux prevents them from accessing arbitrary files)
# A direct workaround is to disable SELinux in factory.

main() {
  # this will set SELinux mode to 'permissive' ==> actions contrary to the
  # policy are logged, but not blocked.
  echo 0 >/sys/fs/selinux/enforce
}

main
