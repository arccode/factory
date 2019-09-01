#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Setup script to install Instalog's Python dependencies in the third_party
# directory.

INSTALOG_DIR="$(dirname "$(readlink -f "$0")")"
REQUIREMENTS_TXT="${INSTALOG_DIR}/requirements.txt"
VIRTUAL_ENV_DIR="${INSTALOG_DIR}/virtual_env"

if ! [ -x "$(command -v virtualenv)" ]; then
  echo "'virtualenv' is not installed!"
  exit 1
fi

rm -fr "${VIRTUAL_ENV_DIR}"
echo "Creating an isolated Python environment by virtualenv."
mkdir "${VIRTUAL_ENV_DIR}"
virtualenv "${VIRTUAL_ENV_DIR}"

source "${VIRTUAL_ENV_DIR}/bin/activate"
echo -n "Installing third-party libraries to the virtual environment..."
# We need to upgrade pip first, or the following line will fail.
pip install --quiet --upgrade pip
pip install --quiet --upgrade -r "${REQUIREMENTS_TXT}"
# If your Python2.7 verion is not 2.7.9+, you can run this line to reduce
# warnings.
# pip install --quiet --upgrade "requests[security]==2.18.0"
echo "done."
deactivate

echo "Finished!"
echo "You can go to the directory '$(dirname ${INSTALOG_DIR})' and"
echo "run Instalog by 'source instalog/virtual_env/bin/activate &&" \
     "python2 instalog [--config /path/to/instalog.yaml] start && deactivate'"
