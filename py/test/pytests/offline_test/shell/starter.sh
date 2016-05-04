#!{%sh%}
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

set -e

DATA_DIR={%data_root%}
TEST_SCRIPT_PATH={%test_script_path%}
LOGFILE="${DATA_DIR}/logfile"

echo "--- Start shell offline test ---" >>"${LOGFILE}"
exec "${TEST_SCRIPT_PATH}" >>"${LOGFILE}" 2>&1
