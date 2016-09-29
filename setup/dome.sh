#!/bin/bash
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# TODO(littlecvr): functionize this file
# TODO(littlecvr): probably should be merged with setup/umpire_docker.sh

set -e

SCRIPT_DIR="$(realpath "$(dirname "${BASH_SOURCE[0]}")")"

. "${SCRIPT_DIR}/cros_docker.sh"

HOST_DOME_DIR="$(realpath "${SCRIPT_DIR}/../py/dome")"
HOST_BUILD_DIR="${HOST_DOME_DIR}/build"

DOCKER_VERSION="1.9.1"
DOME_VERSION="1.0.0"
DOME_IMAGE_FILENAME="dome-${DOME_VERSION}-docker-${DOCKER_VERSION}.tbz"

DOCKER_SHARED_DOME_DIR="${DOCKER_SHARED_DIR}/dome"

DB_FILENAME="db.sqlite3"
BUILDER_WORKDIR="/usr/src/app"
BUILDER_OUTPUT_FILE="frontend.tar"
CONTAINER_DOME_DIR="/var/db/factory/dome"

BUILDER_DOCKERFILE="${HOST_DOME_DIR}/docker/Dockerfile.builder"
DOME_DOCKERFILE="${HOST_DOME_DIR}/docker/Dockerfile.dome"

BUILDER_IMAGE_NAME="cros/dome-builder"
DOME_IMAGE_NAME="cros/dome"

BUILDER_CONTAINER_NAME="dome_builder"
UWSGI_CONTAINER_NAME="dome_uwsgi"
NGINX_CONTAINER_NAME="dome_nginx"

: ${PORT:="8000"}  # port to access Dome

do_build() {
  # build the dome builder image
  docker build \
    --file "${BUILDER_DOCKERFILE}" \
    --tag "${BUILDER_IMAGE_NAME}" \
    --build-arg workdir="${BUILDER_WORKDIR}" \
    --build-arg output_file="${BUILDER_OUTPUT_FILE}" \
    "${HOST_DOME_DIR}"

  # copy the builder's output from container to host
  mkdir -p "${HOST_BUILD_DIR}"
  docker run --name "${BUILDER_CONTAINER_NAME}" "${BUILDER_IMAGE_NAME}"
  docker cp \
    "${BUILDER_CONTAINER_NAME}:${BUILDER_WORKDIR}/${BUILDER_OUTPUT_FILE}" \
    "${HOST_BUILD_DIR}"
  docker rm "${BUILDER_CONTAINER_NAME}"

  # build the dome runner image
  # need to make sure we're using the same version of docker inside the container
  docker build \
    --file "${DOME_DOCKERFILE}" \
    --tag "${DOME_IMAGE_NAME}" \
    --build-arg dome_dir="${CONTAINER_DOME_DIR}" \
    --build-arg builder_output_file="${BUILDER_OUTPUT_FILE}" \
    --build-arg docker_version="$(docker version --format {{.Server.Version}})" \
    "${HOST_DOME_DIR}"
}

do_install() {
  docker load <"${SCRIPT_DIR}/${UMPIRE_IMAGE_FILENAME}"
  docker load <"${SCRIPT_DIR}/${DOME_IMAGE_FILENAME}"
}

do_pull() {
  echo "Pulling Dome Docker image ..."
  if [[ ! -f "${SCRIPT_DIR}/${DOME_IMAGE_FILENAME}" ]]; then
    wget "${PREBUILT_IMAGE_DIR_URL}/${DOME_IMAGE_FILENAME}" || \
      (rm -f "${SCRIPT_DIR}/${DOME_IMAGE_FILENAME}" ; \
       die "Failed to pull Dome Docker image")
  fi
  echo "Finished pulling Dome Docker image"

  echo "Pulling Umpire Docker image..."
  local umpire_image_path="${SCRIPT_DIR}/${UMPIRE_IMAGE_FILENAME}"
  if [[ ! -f "${umpire_image_path}" ]]; then
    local umpire_docker_script="${SCRIPT_DIR}/umpire_docker.sh"
    "${umpire_docker_script}" pull || die "Failed to pull Umpire Docker image"
  fi
  echo "Finished pulling Umpire Docker image"

  # TODO(littlecvr): make a single, self-executable file.
  echo
  echo "All finished, please copy: "
  echo "  1. $(basename "$0") (this script)"
  echo "  2. cros_docker.sh"
  echo "  3. ${DOME_IMAGE_FILENAME}"
  echo "  4. ${UMPIRE_IMAGE_FILENAME}"
  echo "to the target computer."
}

do_run() {
  # stop and remove old containers
  docker stop "${UWSGI_CONTAINER_NAME}" 2>/dev/null || true
  docker rm "${UWSGI_CONTAINER_NAME}" 2>/dev/null || true
  docker stop "${NGINX_CONTAINER_NAME}" 2>/dev/null || true
  docker rm "${NGINX_CONTAINER_NAME}" 2>/dev/null || true

  # make sure database file exists or mounting volume will fail
  if [[ ! -f "${DOCKER_SHARED_DOME_DIR}/${DB_FILENAME}" ]]; then
    echo "Creating docker shared folder (${DOCKER_SHARED_DOME_DIR}),"
    echo "and database file, you'll be asked for root permission..."
    sudo mkdir -p "${DOCKER_SHARED_DOME_DIR}"
    sudo touch "${DOCKER_SHARED_DOME_DIR}/${DB_FILENAME}"
  fi

  # Migrate the database if needed (won't remove any data if the database
  # already exists, but will apply the schema changes). This command may ask
  # user questions and need the user input, so make it interactive.
  docker run \
    --rm \
    --interactive \
    --tty \
    --volume "${DOCKER_SHARED_DOME_DIR}/${DB_FILENAME}:${CONTAINER_DOME_DIR}/${DB_FILENAME}" \
    "${DOME_IMAGE_NAME}" \
    python manage.py migrate

  # start uwsgi, the bridge between django and nginx
  docker run \
    --detach \
    --restart unless-stopped \
    --name "${UWSGI_CONTAINER_NAME}" \
    --volume /var/run/docker.sock:/var/run/docker.sock \
    --volume /run \
    --volume "${DOCKER_SHARED_DOME_DIR}/${DB_FILENAME}:${CONTAINER_DOME_DIR}/${DB_FILENAME}" \
    --volume "${DOCKER_UMPIRE_DIR}:/var/db/factory/umpire" \
    "${DOME_IMAGE_NAME}" \
    uwsgi --ini uwsgi.ini

  # start nginx
  docker run \
    --detach \
    --restart unless-stopped \
    --name "${NGINX_CONTAINER_NAME}" \
    --volumes-from "${UWSGI_CONTAINER_NAME}" \
    --publish "${PORT}:80" \
    "${DOME_IMAGE_NAME}" \
    nginx -g 'daemon off;'

  echo
  echo "Dome is running!"
  echo "Open the browser to http://localhost:${PORT}/ and enjoy!"
}

usage() {
  cat << __EOF__
Dome: the Factory Server Management Console deployment script

commands:
  $0 help
      Show this help message.

  $0 install
      Load Dome and Umpire docker images.

  $0 pull
      Pull Dome and Umpire docker images.

  $0 run
      Create and start Dome containers.

      You can change the listening port (default ${PORT}) by assigning the PORT
      environment variable. For example:

        PORT=1234 $0 run

      will bind port 1234 instead of ${PORT}.

commands for developers:
  $0 build
      Build Dome docker images.

common use case:
  - Run "$0 pull" to download docker images, and copy files listed on screen
    to the target computer.
  - Run "$0 install" on the target computer to load docker images.
  - Run "$0 run" to start Dome.
__EOF__
}

main() {
  # TODO(littlecvr): check /docker_shared
  # TODO(littlecvr): check /docker_umpire
  # TODO(littlecvr): acquire root permission if the user is not in docker group

  case "$1" in
    build)
      do_build
      ;;
    pull)
      do_pull
      ;;
    install)
      do_install
      ;;
    run)
      do_run
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
