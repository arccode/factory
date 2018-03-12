#!/bin/sh
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# http://b/68671587: Change /var/run to be symlink of /run.
#
# Since CL:906889, the /var/run becomes 'mount --bind' instead of symlink.
# This will be a problem for factory wipe_in_place when there are services (for
# example, dhcpcd) using files inside /var/run.  A simple solution is to
# re-create /var/run as symlink.

main() {
  if [ -h /var/run ]; then
    return
  fi

  umount /var/run || true
  rm -rf /var/run
  ln -s /run /var/run
}

main "$@"
