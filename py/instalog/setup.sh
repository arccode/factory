#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Setup script to install Instalog's Python dependencies in the external
# directory.

INSTALOG_DIR="$(dirname "$(readlink -f "$0")")"
REQUIREMENTS_TXT="${INSTALOG_DIR}/requirements.txt"
EXTERNAL_DIR="${INSTALOG_DIR}/external"

echo "Installing external libraries to ${EXTERNAL_DIR}..."
rm -fr "${EXTERNAL_DIR}"
pip install -t "${EXTERNAL_DIR}" -r "${REQUIREMENTS_TXT}"
