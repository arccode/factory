#!/bin/bash
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# This scripts loads the board setup script first then invokes
# factory.py for miscellaneous factory actions.

FACTORY_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")"
BOARD_SETUP_SCRIPT="${FACTORY_DIR}/board/board_setup_factory.sh"

# Load the board setup script to get CROS_FACTORY_DUT_OPTIONS.
if [ -s "${BOARD_SETUP_SCRIPT}" ]; then
  echo "Loading board-specific parameters ${BOARD_SETUP_SCRIPT}..."
  . "${BOARD_SETUP_SCRIPT}"
fi

"${FACTORY_DIR}/bin/factory_env" "${FACTORY_DIR}/py/tools/factory.py" "$@"
