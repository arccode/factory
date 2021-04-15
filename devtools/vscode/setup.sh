#!/usr/bin/env bash
# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Usage: ./setup.sh
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
set -e
. "${SCRIPT_DIR}/../mk/common.sh"

CODE_DIR="${SCRIPT_DIR}/../../.vscode"
mkdir -p "${CODE_DIR}"
cp -f "${SCRIPT_DIR}/factory_settings.json" "${CODE_DIR}/settings.json"
echo "Add .vscode to your global .gitignore."
echo "See https://gist.github.com/subfuzion/db7f57fff2fb6998a16c for more" \
  "information."
mk_success
