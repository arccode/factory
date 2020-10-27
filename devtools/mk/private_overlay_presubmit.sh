#!/usr/bin/env bash
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This is presubmit check for private overlay to check the health of test lists.
# Example CL : go/croscli/3164743.

if [[ "${PRESUBMIT_PROJECT}" =~ chromeos/overlays/overlay-(.+)-private ]]; then
  board="${BASH_REMATCH[1]}"
else
  exit 0
fi

test_list_ids=""
for file in ${PRESUBMIT_FILES}
do
  filename="$(basename "${file}")"
  if [[ "${filename}" =~ (.+).test_list.json ]]; then
    test_list_ids="${test_list_ids} ${BASH_REMATCH[1]}"
  fi
done

if [ -z "$test_list_ids" ]; then
  exit 0
fi

if [ -f /etc/debian_chroot ]; then
  factory_dir="$(dirname "$(dirname " $(dirname "$(readlink -f "$0")")")")"
  test_list_checker_path="${factory_dir}/bin/test_list_checker"

  # Clean up these env variables. Without doing this, we will get additional
  # errors when test_list_checker report errors. The reason is that
  # test_list_checker uses the Makefile, and in the Makefile, we try to read the
  # path from PRESUBMIT_FILES.
  PRESUBMIT_FILES="" PRESUBMIT_COMMIT="" PRESUBMIT_PROJECT="" \
      ${test_list_checker_path} --board "${board}" ${test_list_ids}
else
  exec cros_sdk --working-dir=. PRESUBMIT_FILES="${PRESUBMIT_FILES}" \
      PRESUBMIT_COMMIT="${PRESUBMIT_COMMIT}" \
      PRESUBMIT_PROJECT="${PRESUBMIT_PROJECT}" -- "$0"
fi
