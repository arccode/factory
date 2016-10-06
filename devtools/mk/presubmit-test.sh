#!/bin/bash
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
. "${SCRIPT_DIR}/common.sh" || exit 1

main() {
  local changed
  if [ ! -e .tests-passed ]; then
      die 'Unit tests have not passed.  Please run "make test".'
  fi

  if [ -n "$@" ]; then
    # TODO(hungte) skip doc/%
    changed="$(find "$@" -type f -newer .tests-passed)"
  elif [ "$(git log -1 --format=%ct)" -gt "$(stat -c %Y .tests-passed)" ]; then
    changed="one or more deleted files"
  fi

  if [ -n "${changed}" ]; then
    echo "Files have changed since last time unit tests passed:"
    echo "${changed}" | sed -e 's/^/  /'
    die 'Please run "make test" inside chroot.'
  fi
  mk_success
}
main "$@"
