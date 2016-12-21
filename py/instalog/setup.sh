#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Setup script to install Instalog's Python dependencies in the third_party
# directory.

INSTALOG_DIR="$(dirname "$(readlink -f "$0")")"
REQUIREMENTS_TXT="${INSTALOG_DIR}/requirements.txt"
THIRD_PARTY_DIR="${INSTALOG_DIR}/third_party"

echo "Installing third-party libraries to ${THIRD_PARTY_DIR}..."
rm -fr "${THIRD_PARTY_DIR}"
pip install -t "${THIRD_PARTY_DIR}" -r "${REQUIREMENTS_TXT}"
