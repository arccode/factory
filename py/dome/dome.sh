#!/bin/bash
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# TODO(littlecvr): functionize this file
# TODO(littlecvr): probably should be merged with setup/umpire_docker.sh

set -e

SCRIPT_DIR=$(realpath $(dirname "${BASH_SOURCE[0]}"))

DOCKER_SHARED_DIR="/docker_shared/dome"
DOCKER_UMPIRE_DIR="/docker_umpire"

DB_FILE="db.sqlite3"
BUILDER_WORKDIR="/usr/src/app"
BUILDER_OUTPUT_FILE="frontend.tar"
DOME_DIR="/var/db/factory/dome"

BUILDER_DOCKERFILE="docker/Dockerfile.builder"
DOME_DOCKERFILE="docker/Dockerfile.dome"

BUILDER_IMAGE_NAME="cros/dome-builder"
DOME_IMAGE_NAME="cros/dome"

BUILDER_CONTAINER_NAME="dome_builder"
UWSGI_CONTAINER_NAME="dome_uwsgi"
NGINX_CONTAINER_NAME="dome_nginx"

DOME_PORT="8000"

# stop existing containers if needed
docker stop "${BUILDER_CONTAINER_NAME}" 2>/dev/null || true
docker rm "${BUILDER_CONTAINER_NAME}" 2>/dev/null || true
docker stop "${UWSGI_CONTAINER_NAME}" 2>/dev/null || true
docker rm "${UWSGI_CONTAINER_NAME}" 2>/dev/null || true
docker stop "${NGINX_CONTAINER_NAME}" 2>/dev/null || true
docker rm "${NGINX_CONTAINER_NAME}" 2>/dev/null || true

# build the dome builder image
docker build \
  --file "${SCRIPT_DIR}/${BUILDER_DOCKERFILE}" \
  --tag "${BUILDER_IMAGE_NAME}" \
  --build-arg workdir="${BUILDER_WORKDIR}" \
  --build-arg output_file="${BUILDER_OUTPUT_FILE}" \
  "${SCRIPT_DIR}"

# copy the builder's output from container to host
mkdir -p "${SCRIPT_DIR}/build"
docker run --name "${BUILDER_CONTAINER_NAME}" "${BUILDER_IMAGE_NAME}"
docker cp \
  "${BUILDER_CONTAINER_NAME}:${BUILDER_WORKDIR}/${BUILDER_OUTPUT_FILE}" \
  "${SCRIPT_DIR}/build/"
docker rm "${BUILDER_CONTAINER_NAME}"

# build the dome runner image
# need to make sure we're using the same version of docker inside the container
docker build \
  --file "${SCRIPT_DIR}/${DOME_DOCKERFILE}" \
  --tag "${DOME_IMAGE_NAME}" \
  --build-arg dome_dir="${DOME_DIR}" \
  --build-arg builder_output_file="${BUILDER_OUTPUT_FILE}" \
  --build-arg docker_version="$(docker version --format {{.Server.Version}})" \
  "${SCRIPT_DIR}"

# make sure database file exists or mounting volume will fail
mkdir -p "${DOCKER_SHARED_DIR}"
touch "${DOCKER_SHARED_DIR}/${DB_FILE}"

# Migrate the database if needed (won't remove any data if the database already
# exists, but will apply the schema changes). This command may ask user
# questions and need the user input, so make it interactive.
docker run \
  --rm \
  --interactive \
  --tty \
  --volume "${DOCKER_SHARED_DIR}/${DB_FILE}:${DOME_DIR}/${DB_FILE}" \
  "${DOME_IMAGE_NAME}" \
  python manage.py migrate

# start uwsgi, the bridge between django and nginx
docker run \
  --detach \
  --restart unless-stopped \
  --name "${UWSGI_CONTAINER_NAME}" \
  --volume /var/run/docker.sock:/var/run/docker.sock \
  --volume /run \
  --volume "${DOCKER_SHARED_DIR}/${DB_FILE}:${DOME_DIR}/${DB_FILE}" \
  --volume "${DOCKER_UMPIRE_DIR}:/var/db/factory/umpire" \
  "${DOME_IMAGE_NAME}" \
  uwsgi --ini uwsgi.ini

# start nginx
docker run \
  --detach \
  --restart unless-stopped \
  --name "${NGINX_CONTAINER_NAME}" \
  --volumes-from "${UWSGI_CONTAINER_NAME}" \
  --publish ${DOME_PORT}:80 \
  "${DOME_IMAGE_NAME}" \
  nginx -g 'daemon off;'
