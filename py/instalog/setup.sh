#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Setup script to install Instalog's Python dependencies in the third_party
# directory.

INSTALOG_DIR="$(dirname "$(readlink -f "$0")")"
REQUIREMENTS_TXT="${INSTALOG_DIR}/requirements.txt"
VIRTUAL_ENV_DIR="${INSTALOG_DIR}/virtual_env"

rm -fr "${VIRTUAL_ENV_DIR}"
echo "Creating an isolated Python3 environment by virtualenv."
mkdir "${VIRTUAL_ENV_DIR}"
# venv is new in Python3.3
python3 -m venv "${VIRTUAL_ENV_DIR}"

source "${VIRTUAL_ENV_DIR}/bin/activate"
echo -n "Installing third-party libraries to the virtual environment..."
# We need to upgrade pip first, or the following line will fail.
pip3 install --quiet --upgrade --no-cache-dir pip
pip3 install --quiet --upgrade --no-cache-dir wheel
pip3 install --quiet --upgrade --no-cache-dir -r "${REQUIREMENTS_TXT}"
echo "done."
deactivate

echo "Finished!"
echo "You can go to the directory '$(dirname ${INSTALOG_DIR})' and"
echo "run Instalog by 'source instalog/virtual_env/bin/activate &&" \
     "python3 /path/to/factory/bin/instalog" \
     "[--config /path/to/instalog.yaml] start && deactivate'"
