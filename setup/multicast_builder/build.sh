#!/bin/sh
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

CONTAINER_NAME="mcast_builder"
DOCKERFILE="Dockerfile.builder"
GSUTIL_BUCKET="gs://chromeos-localmirror/distfiles"
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
UFTP_BINARY="uftp"
UFTP_TARBALL="uftp-4.10.1.tar.gz"

docker build \
  --file "${DOCKERFILE}" \
  --tag "${CONTAINER_NAME}" \
  "${SCRIPT_DIR}"

mkdir "${SCRIPT_DIR}/build"

docker_id=$(docker create ${CONTAINER_NAME})

docker cp "${docker_id}:build/${UFTP_BINARY}" "${SCRIPT_DIR}/build"
# Override modify time and compression command to make the hash stable.
tar -C "${SCRIPT_DIR}/build/" -cf "${SCRIPT_DIR}/build/${UFTP_TARBALL}" \
  --mtime "1970-01-01" -I "gzip --no-name" "${UFTP_BINARY}"
gsutil cp "${SCRIPT_DIR}/build/${UFTP_TARBALL}" \
  "${GSUTIL_BUCKET}/${UFTP_TARBALL}"
gsutil acl ch -u AllUsers:R "${GSUTIL_BUCKET}/${UFTP_TARBALL}"
