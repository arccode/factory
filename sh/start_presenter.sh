#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Start the presenter on a non-ChromeOS device

has_executable() {
  type "$1" >/dev/null 2>&1
}

has_python_package() {
  python -c "import $1" >/dev/null 2>&1
}

check_missing_prerequisites() {
  has_executable google-chrome || echo "Google Chrome"
  has_executable python || echo "Python"
  has_python_package "yaml" || echo "python-yaml package"
  has_python_package "netifaces" || echo "python-netifaces package"
  has_python_package "numpy" || echo "python-numpy package"
  has_python_package "jsonrpclib" || echo "python-jsonrpclib package"
  has_python_package "ws4py" || echo "python-ws4py package"
  has_python_package "dpkt" || echo "python-dpkt package"
}

MISSING_PREREQUISITES="$(check_missing_prerequisites)"
if [ -n "${MISSING_PREREQUISITES}" ]; then
  echo "The following packages are missing. Please install and retry:"
  echo "${MISSING_PREREQUISITES}" | sed 's/^/  /'
  exit 1
fi

FACTORY_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")"
IPTABLESD="${FACTORY_DIR}/init/iptables.d"

# Load iptables rules
for rule_file in ${IPTABLESD}/*.sh; do
  "$rule_file"
done

# Start presenter frontend and backend
TMP_DATA_DIR=""
CHROME_PID=""

clean_up() {
  [ -n "${TMP_DATA_DIR}" ] && rm -f "${TMP_DATA_DIR}"
  [ -n "${CHROME_PID}" ] && kill "${CHROME_PID}"
}

trap clean_up EXIT
TMP_DATA_DIR="$(mktemp -d --tmpdir || mktemp -d)"
google-chrome \
  --load-and-launch-app="${FACTORY_DIR}/py/goofy/ui_presenter_app" \
  chrome-extension://oaaomfgfdeefdhpfbokkpkhodmjaicoh/main.html \
  --user-data-dir="${TMP_DATA_DIR}" \
  --disable-translate \
  --overscroll-history-navigation=0 &
CHROME_PID="$!"
"${FACTORY_DIR}/py/goofy/goofy_presenter.py"
