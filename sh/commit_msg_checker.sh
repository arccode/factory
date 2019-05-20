#!/bin/bash
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# This script checks if commit message contains word which is sensitive to
# factory.

readonly commit_desc="$(git log --format=%s%n%n%b "${PRESUBMIT_COMMIT}^!")"
readonly sensitive_build_stages=("MP" "PVT" "DVT" "EVT" "PROTO")

# Data source: https://www.chromium.org/chromium-os/developer-information-for-chrome-os-devices
readonly sensitive_oems=("ACER" "AOPEN" "ASUS" "CTL" "DELL" "HP" "LENOVO" "LG"
  "PCMERGE" "POIN2" "SAMSUNG" "TOSHIBA" "VIEWSONIC")

echo "EXPECT_SENSITIVE_BUILD_STAGES = ${EXPECT_SENSITIVE_BUILD_STAGES}"
echo "EXPECT_SENSITIVE_OEMS = ${EXPECT_SENSITIVE_OEMS}"

if [ "${EXPECT_SENSITIVE_BUILD_STAGES}" != "true" ]; then
  for stage in "${sensitive_build_stages[@]}"; do
    grep_result=$(echo "${commit_desc}" | grep -wi "${stage}")
    if [[ ! -z "${grep_result}" ]]; then
      echo "Commit message contains sensitive word ${stage}, please fix it."
      echo "If your build stage usage ${stage} is reasonable,"\
        "skip the check by EXPECT_SENSITIVE_BUILD_STAGES=true repo upload"
      exit 1
    fi
  done
else
  echo "EXPECT_SENSITIVE_BUILD_STAGES is set to true, skip build stage check."
fi

if [ "${EXPECT_SENSITIVE_OEMS}" != "true" ]; then
  for name in "${sensitive_oems[@]}"; do
    grep_result="$(echo "${commit_desc}" | grep -wi "${name}")"
    if [[ ! -z "${grep_result}" ]]; then
      echo "Commit message contains sensitive word ${name}, please fix it."
      echo "If your OEM name usage ${name} is reasonable,"\
        "skip the check by EXPECT_SENSITIVE_OEMS=true repo upload"
      exit 1
    fi
  done
else
  echo "EXPECT_SENSITIVE_OEMS is set to true, skip OEM name check."
fi

exit 0
