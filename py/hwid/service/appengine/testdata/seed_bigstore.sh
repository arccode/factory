#!/bin/bash
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script helps uploading test data to local dev server.
# To seed your dev instance, run this script inside the testdata directory. You
# will have to disable the admin restriction on the ingestion handler in
# app.yaml first.

: ${SERVER:=localhost:8080}
: ${COOKIE_FILE:="/tmp/dev_appserver_auth_cookies.txt"}
: ${DIR:=bigstore}

# Uploads a file to the server with the given target name in staging.
upload() {
  local file=$1
  local target=$2

  curl --silent --show-error \
    -b "${COOKIE_FILE}" \
    -X POST \
    -F "path=staging/${target}" \
    -F data=@${file} \
    "http://${SERVER}/ingestion/upload" > /dev/null
}

# Authenticate
curl "http://${SERVER}/_ah/login" \
  -d "email=test@example.com&action=Log+In&admin=True" \
  -c "${COOKIE_FILE}"

for file in ${DIR}/*;
do
  echo -n "Uploading ${file}..."
  base=$(basename ${file})
  upload ${file} ${base}
  echo "Done."
done;

curl -b "${COOKIE_FILE}" "http://${SERVER}/ingestion/refresh"
