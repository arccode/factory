#!/bin/bash
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

DOCKER_VERSION="1.9.1"

PREBUILT_IMAGE_SITE="https://storage.googleapis.com"
PREBUILT_IMAGE_DIR_URL="${PREBUILT_IMAGE_SITE}/chromeos-localmirror/distfiles"

GSUTIL_BUCKET="gs://chromeos-localmirror/distfiles"

DOCKER_SHARED_DIR="/docker_shared"
DOCKER_UMPIRE_DIR="/docker_umpire"

UMPIRE_CONTAINER_NAME="umpire"
UMPIRE_IMAGE_NAME="cros/umpire"
UMPIRE_BUILD_DIR="${SCRIPT_DIR}/umpire_docker"

UMPIRE_IMAGE_VERSION="20161118161051"  # timestamp
UMPIRE_IMAGE_FILENAME="umpire-${UMPIRE_IMAGE_VERSION}-docker-${DOCKER_VERSION}.txz"

TEMP_OBJECTS=()

on_exit() {
  # clear all temp objects
  for t in "${TEMP_OBJECTS[@]}"; do
    echo "Removing temp object ${t}"
    rm -rf "${t}"
  done
  TEMP_OBJECTS=()
}
trap on_exit EXIT

die() {
  echo "ERROR: $@"
  exit 1
}

warn() {
  echo "WARNING: $@"
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

  # check Docker version
  local docker_version="$(${DOCKER} version --format={{.Server.Version}})"
  local error_message="Require Docker version >= ${DOCKER_VERSION} but you have ${docker_version}"
  local required_version=(${DOCKER_VERSION//./ })
  local current_version=(${docker_version//./ })
  for ((i = 0; i < ${#required_version[@]}; ++i)); do
    if (( ${#current_version[@]} <= $i )); then
      die "${error_message}"  # the current version array is not long enough
    elif (( ${required_version[$i]} < ${current_version[$i]} )); then
      break
    elif (( ${required_version[$i]} > ${current_version[$i]} )); then
      die "${error_message}"
    fi
  done
}

check_gsutil() {
  if ! type gsutil >/dev/null 2>&1; then
    die "Cannot find gsutil, please install gsutil first"
  fi
}

upload_to_localmirror() {
  local local_file_path="$1"
  local remote_file_url="$2"

  echo "Uploading to chromeos-localmirror"
  gsutil cp "${local_file_path}" "${remote_file_url}"
  gsutil acl ch -u AllUsers:R "${remote_file_url}"
}
