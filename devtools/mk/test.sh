#!/bin/bash
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
. "${SCRIPT_DIR}/common.sh" || exit 1

# Current script should be in ${FACTORY_REPO}/devtools/mk.
: ${FACTORY_REPO:="$(dirname "$(dirname "${SCRIPT_DIR}")")"}
# Common definitions
: ${TEST_RUNNER:=py/tools/run_tests.py}
: ${TEST_EXTRA_FLAGS:=}
# Maximum number of parallel tests to run.
: ${MAX_TESTS:=}
# Tests need to run in isolate mode.
: ${TEST_ISOLATE_LIST:=}

main() {
  local tests="$@"
  local rootdir="${FACTORY_REPO}"

  # Make sure all python code will be re-evaluated.
  info "Clear Python compiled cache..."
  find "${rootdir}" '(' -name '.wh..wh.*' -prune -o -name '*' ')' \
      -a -name '*.pyc' -exec rm -f {} ';' >/dev/null 2>&1

  local logdir="/tmp/test.logs.$(date +%Y%m%d_%H%M%S)"
  mkdir -p "${logdir}"

  info "Test logs will be written to ${logdir}..."

  if [ ! -d "${rootdir}/../../private-overlays" ]; then
    warn "Private components are missing." \
         "Some tests are likely to fail without them."
    sleep 1  # Short delay to make sure developers see this.
  fi

  # Determine test parameters
  if [ -z "${MAX_TESTS}" ]; then
    MAX_TESTS="$(grep -c ^processor /proc/cpuinfo)"
  fi
  if [ -n "${TEST_ISOLATE_LIST}" ]; then
    # TODO(sheckylin): Get py/test/utils/media_utils_unittest.py working.
    TEST_EXTRA_FLAGS+=" -i='${TEST_ISOLATE_LIST}' "
  fi

  # Run tests with POSIX locale to avoid localized output.
  LC_ALL=C "${TEST_RUNNER}" --jobs "${MAX_TESTS}" --log "${logdir}" \
    ${TEST_EXTRA_FLAGS} ${tests}

  mk_success
}
main "$@"
