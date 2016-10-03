#!/bin/bash
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(realpath "$(dirname "${BASH_SOURCE[0]}")")"

PREBUILT_IMAGE_SITE='https://storage.googleapis.com'
PREBUILT_IMAGE_DIR_URL="${PREBUILT_IMAGE_SITE}/chromeos-localmirror/distfiles"

DOCKER_SHARED_DIR="/docker_shared"
DOCKER_UMPIRE_DIR="/docker_umpire"

UMPIRE_CONTAINER_NAME="umpire"
UMPIRE_IMAGE_NAME="cros/umpire"
UMPIRE_BUILD_DIR="${SCRIPT_DIR}/umpire_docker"

# We use the md5sum of the Dockerfile to know if the prebuilt image of this
# Dockerfile is in server.
UMPIRE_IMAGE_HASH="$(md5sum "${UMPIRE_BUILD_DIR}/Dockerfile" | cut -c1-5)"
UMPIRE_IMAGE_FILENAME="docker_umpire_env-${UMPIRE_IMAGE_HASH}.tbz"

die() {
  echo "ERROR: $@"
  exit 1
}

check_docker() {
  if ! type docker >/dev/null 2>&1; then
    die "Docker not installed, abort."
  fi
  DOCKER="docker"
  if [ "${USER}" != "root" ]; then
    if ! echo begin $(id -Gn) end | grep -q ' docker '; then
      echo "You are neither root nor in the docker group,"
      echo "so you'll be asked for root permission..."
      DOCKER="sudo docker"
    fi
  fi
}
