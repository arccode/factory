#!/bin/bash
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

set -e

# Utility functions
DOCKER_VERSION="1.10.3"
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
  echo "ERROR: $*"
  exit 1
}

warn() {
  echo "WARNING: $*"
}

realpath() {
  # Try to find "realpath" in a portable way.
  if type python >/dev/null 2>&1; then
    python -c 'import sys; import os; print os.path.realpath(sys.argv[1])' "$1"
  else
    readlink -f "$@"
  fi
}

check_docker() {
  if ! type docker >/dev/null 2>&1; then
    die "Docker not installed, abort."
  fi
  DOCKER="docker"
  if [ "$(id -un)" != "root" ]; then
    if ! echo "begin $(id -Gn) end" | grep -q " docker "; then
      echo "You are neither root nor in the docker group,"
      echo "so you'll be asked for root permission..."
      DOCKER="sudo docker"
    fi
  fi

  # Check Docker version
  local docker_version="$(${DOCKER} version --format '{{.Server.Version}}' \
                          2>/dev/null)"
  if [ -z "${docker_version}" ]; then
    # Old Docker (i.e., 1.6.2) does not support --format.
    docker_version="$(${DOCKER} version | sed -n 's/Server version: //p')"
  fi
  local error_message="Require Docker version >= ${DOCKER_VERSION} but you have ${docker_version}"
  local required_version=(${DOCKER_VERSION//./ })
  local current_version=(${docker_version//./ })
  for ((i = 0; i < ${#required_version[@]}; ++i)); do
    if (( ${#current_version[@]} <= i )); then
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

check_xz() {
  XZ="pixz"
  if ! type pixz >/dev/null 2>&1; then
    warn "pixz is not installed, fall back to xz, compression will be slow!!!"
    warn "Install pixz if you don't want to wait for too long"
    XZ="xz"
  fi
}

upload_to_localmirror() {
  local local_file_path="$1"
  local remote_file_url="$2"

  echo "Uploading to chromeos-localmirror"
  gsutil cp "${local_file_path}" "${remote_file_url}"
  gsutil acl ch -u AllUsers:R "${remote_file_url}"
}

# Base directories
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
FACTORY_DIR="$(dirname "${SCRIPT_DIR}")"
UMPIRE_DIR="${FACTORY_DIR}/py/umpire"
DOME_DIR="${FACTORY_DIR}/py/dome"
BUILD_DIR="${FACTORY_DIR}/build/docker"

# Directories on host that would be mounted to docker
# This would be overriden in integration tests.
: "${HOST_SHARED_DIR:="/cros_docker"}"
HOST_DOME_DIR="${HOST_SHARED_DIR}/dome"
HOST_UMPIRE_DIR="${HOST_SHARED_DIR}/umpire"
HOST_OVERLORD_DIR="${HOST_SHARED_DIR}/overlord"
HOST_OVERLORD_APP_DIR="${HOST_OVERLORD_DIR}/app"

# Publish tools
PREBUILT_IMAGE_SITE="https://storage.googleapis.com"
PREBUILT_IMAGE_DIR_URL="${PREBUILT_IMAGE_SITE}/chromeos-localmirror/distfiles"
GSUTIL_BUCKET="gs://chromeos-localmirror/distfiles"
CHANGES_FILE=
COMMIT_SUBJECT="setup: Publish cros_docker image version"

# Remote resources
RESOURCE_DOCKER_URL="https://get.docker.com/builds/Linux/i386/docker-${DOCKER_VERSION}.tgz"
RESOURCE_DOCKER_SHA1="0b2619a77d0513d4e503120ad17e2ca09e6176ad"
RESOURCE_CROS_DOCKER_URL="https://chromium.googlesource.com/chromiumos/platform/factory/+/master/setup/cros_docker.sh?format=TEXT"

# Directories inside docker
DOCKER_BASE_DIR="/usr/local/factory"
DOCKER_DOME_DIR="${DOCKER_BASE_DIR}/py/dome"
DOCKER_UMPIRE_DIR="${DOCKER_BASE_DIR}/py/umpire"
DOCKER_INSTALOG_DIR="${DOCKER_BASE_DIR}/py/instalog"

DOCKER_OVERLORD_DIR="${DOCKER_BASE_DIR}/bin/overlord"
DOCKER_OVERLORD_APP_DIR="${DOCKER_OVERLORD_DIR}/app"

# Umpire's db directory mount point in Dome
DOCKER_UMPIRE_DIR_IN_DOME="/var/db/factory/umpire"

# DOCKER_IMAGE_{GITHASH,TIMESTAMP} will be updated when you publish.
DOCKER_IMAGE_GITHASH="f84a8972ce484d53beccd566b350f8a032213f58"
DOCKER_IMAGE_TIMESTAMP="20170620164005"
DOCKER_IMAGE_NAME="cros/factory_server"

# Configures docker image file information by DOCKER_IMAGE_{GITHASH,TIMESTAMP}.
set_docker_image_info() {
  DOCKER_IMAGE_BUILD="${DOCKER_IMAGE_TIMESTAMP}-${DOCKER_IMAGE_GITHASH:0:6}"
  DOCKER_IMAGE_VERSION="${DOCKER_IMAGE_BUILD}-docker-${DOCKER_VERSION}"
  DOCKER_IMAGE_FILENAME="factory-server-${DOCKER_IMAGE_VERSION}.txz"
  DOCKER_IMAGE_FILEPATH="${SCRIPT_DIR}/${DOCKER_IMAGE_FILENAME}"
}
# Set DOCKER_IMAGE_* variables immediately.
set_docker_image_info

# Things that can be override by environment variable
: "${BOARD:="$(cat "${HOST_UMPIRE_DIR}/.default_board" 2>/dev/null)"}"
: "${BOARD:="default"}"
: "${UMPIRE_CONTAINER_NAME:="umpire_${BOARD}"}"
: "${UMPIRE_CONTAINER_DIR:="${BOARD}"}"
: "${UMPIRE_PORT:="8080"}"  # base port for Umpire
: "${DOME_PORT:="8000"}"  # port to access Dome
: "${OVERLORD_HTTP_PORT:="9000"}"  # port to access Overlord

ensure_dir() {
  local dir="$1"
  if [ ! -d "${dir}" ]; then
    sudo mkdir -p "${dir}"
  fi
}

ensure_dir_acl() {
  local dir="$1"
  # On Mac, osxfs needs the folder to be owned by current user.
  if [ "$(uname -s)" = "Darwin" ]; then
    sudo chown -R "$(id -u)" "${dir}"
    sudo chgrp -R "$(id -g)" "${dir}"
  fi
}

fetch_resource() {
  local local_name="$1"
  local url="$2"
  local sha1="$3"

  if [[ ! -f "${local_name}" ]] || \
     ! echo "${sha1} ${local_name}" | sha1sum -c; then
    rm -f "${local_name}"
    curl -L --fail "${url}" -o "${local_name}" || rm -f "${local_name}"
  fi
}

# Section for Umpire subcommand
do_umpire_run() {
  check_docker

  # Separate umpire db for each container.
  local host_db_dir="${HOST_UMPIRE_DIR}/${UMPIRE_CONTAINER_DIR}"
  local docker_db_dir="/var/db/factory/umpire"

  ensure_dir "${HOST_SHARED_DIR}"
  ensure_dir "${host_db_dir}"
  ensure_dir_acl "${HOST_SHARED_DIR}"

  # TODO(pihsun): We should stop old container like what dome run does.
  echo "Starting Umpire container ..."

  if ${DOCKER} ps --all --format '{{.Names}}' | \
      grep -q "^${UMPIRE_CONTAINER_NAME}$"; then
    if ! ${DOCKER} ps --all --format '{{.Names}} {{.Image}}' | \
        grep "^${UMPIRE_CONTAINER_NAME}\ ${DOCKER_IMAGE_NAME}$"; then
      warn "A container with name ${UMPIRE_CONTAINER_NAME} exists," \
           "but is using an old image."
    fi
    ${DOCKER} start "${UMPIRE_CONTAINER_NAME}"
  else
    local p1=${UMPIRE_PORT}              # Imaging & Shopfloor
    local p2=$((UMPIRE_PORT + 2))  # CLI RPC
    local p3=$((UMPIRE_PORT + 4))  # Rsync
    # TODO(chuntsen): Remove instalog_socket_port.
    local p4=$((UMPIRE_PORT + 6))  # Instalog input_socket

    local umpire_base_port=8080
    local umpire_cli_port=$((umpire_base_port + 2))
    local umpire_rsync_port=$((umpire_base_port + 4))
    # TODO(chuntsen): Remove instalog_socket_port.
    local umpire_instalog_socket_port=$((umpire_base_port + 6))

    ${DOCKER} run \
      --detach \
      --restart unless-stopped \
      --name "${UMPIRE_CONTAINER_NAME}" \
      --tmpfs "/run:rw,size=16384k" \
      --volume /etc/localtime:/etc/localtime:ro \
      --volume "${HOST_SHARED_DIR}:/mnt" \
      --volume "${host_db_dir}:${docker_db_dir}" \
      --publish "${p1}:${umpire_base_port}" \
      --publish "${p2}:${umpire_cli_port}" \
      --publish "${p3}:${umpire_rsync_port}" \
      --publish "${p4}:${umpire_instalog_socket_port}" \
      --privileged \
      "${DOCKER_IMAGE_NAME}" \
      "${DOCKER_BASE_DIR}/bin/umpired" || \
      (echo "Removing stale container due to error ..."; \
       ${DOCKER} rm "${UMPIRE_CONTAINER_NAME}"; \
       die "Can't start umpire docker. Possibly wrong port binding?")
  fi

  echo "done"
  echo
  echo "*** NOTE ***"
  echo "- Host directory ${HOST_SHARED_DIR} is mounted" \
       "under /mnt in the container."
  echo "- Host directory ${host_db_dir} is mounted" \
       "under ${docker_db_dir} in the container."
  echo "- Umpire service ports is mapped to the local machine."
}

do_umpire_stop() {
  check_docker

  echo -n "Stopping ${UMPIRE_CONTAINER_NAME} container ... "
  ${DOCKER} stop "${UMPIRE_CONTAINER_NAME}" >/dev/null 2>&1 || true
  echo "done"
}

do_umpire_destroy() {
  check_docker

  echo -n "Deleting ${UMPIRE_CONTAINER_NAME} container ... "
  ${DOCKER} stop "${UMPIRE_CONTAINER_NAME}" >/dev/null 2>&1 || true
  ${DOCKER} rm "${UMPIRE_CONTAINER_NAME}" >/dev/null 2>&1 || true
  echo "done"
}

check_umpire_status() {
  local container_name="$1"
  if ! ${DOCKER} ps --format "{{.Names}} {{.Status}}" \
    | grep -q "${container_name} Up "; then
    die "${container_name} container is not running"
  fi
}

do_umpire_shell() {
  check_docker
  check_umpire_status "${UMPIRE_CONTAINER_NAME}"

  ${DOCKER} exec -it "${UMPIRE_CONTAINER_NAME}" sh
}

do_umpire_test() {
  check_docker

  do_build

  local umpire_tester_image_name="cros/umpire_tester"
  local dockerfile="${UMPIRE_DIR}/e2e_test/Dockerfile"

  fetch_resource "${BUILD_DIR}/docker.tgz" \
    "${RESOURCE_DOCKER_URL}" "${RESOURCE_DOCKER_SHA1}"

  ${DOCKER} build \
    --file "${dockerfile}" \
    --tag "${umpire_tester_image_name}" \
    --build-arg server_dir="${DOCKER_BASE_DIR}" \
    --build-arg umpire_dir="${DOCKER_UMPIRE_DIR}" \
    "${FACTORY_DIR}"

  local temp_dir="$(mktemp -d)"
  TEMP_OBJECTS=("${temp_dir}" "${TEMP_OBJECTS[@]}")

  ${DOCKER} run \
    --rm \
    --net=host \
    --volume /etc/localtime:/etc/localtime:ro \
    --volume "${temp_dir}:${temp_dir}" \
    --volume /run/docker.sock:/run/docker.sock \
    --volume /run \
    --env "TMPDIR=${temp_dir}" \
    --env "LOG_LEVEL=${LOG_LEVEL}" \
    "${umpire_tester_image_name}" \
    "${DOCKER_UMPIRE_DIR}/e2e_test/e2e_test.py" "$@"
}

umpire_usage() {
  cat << __EOF__
Umpire: the Unified Factory Server deployment script

You can change target Umpire container (default ${UMPIRE_CONTAINER_NAME}) by
assigning the UMPIRE_CONTAINER_NAME environment variable.

commands:
  $0 umpire help
      Show this help message.

  $0 umpire run
      Create and start Umpire containers.

      You can change the umpire base port (default ${UMPIRE_PORT}) by assigning
      the UMPIRE_PORT environment variable.
      Umpire would bind base_port, base_port+2, base_port+4 and base_port+6.
      For example:

        UMPIRE_PORT=1234 $0 umpire run

      will change umpire base port to 1234 instead of ${UMPIRE_PORT}.

  $0 umpire stop
      Stop Umpire container.

commands for developers:
  $0 umpire destroy
      Destroy Umpire container.

  $0 umpire shell
      Invoke a shell inside Umpire container.

  $0 umpire test [args...]
      Run integration test for Umpire docker. This would take a while.
      Extra arguments would be passed to the test script.
__EOF__
}

umpire_main() {
  case "$1" in
    run)
      do_umpire_run
      ;;
    stop)
      do_umpire_stop
      ;;
    destroy)
      do_umpire_destroy
      ;;
    shell)
      do_umpire_shell
      ;;
    test)
      shift
      do_umpire_test "$@"
      ;;
    *)
      umpire_usage
      exit 1
      ;;
  esac
}

# Section for Overlord subcommand
do_overlord_setup() {
  check_docker

  local overlord_setup_container_name="overlord_setup"

  echo "Doing setup for Overlord, you'll be asked for root permission ..."
  sudo rm -rf "${HOST_OVERLORD_DIR}"
  ensure_dir "${HOST_OVERLORD_DIR}"
  ensure_dir_acl "${HOST_SHARED_DIR}"

  local temp_docker_id
  temp_docker_id=$(${DOCKER} create ${DOCKER_IMAGE_NAME})

  # We always need sudo for this command for writing permission for
  # HOST_OVERLORD_DIR.
  sudo docker cp \
    "${temp_docker_id}:${DOCKER_OVERLORD_APP_DIR}" \
    "${HOST_OVERLORD_DIR}"
  ${DOCKER} rm "${temp_docker_id}"

  echo "Running setup script ..."
  echo

  ${DOCKER} run \
    --interactive \
    --tty \
    --rm \
    --name "${overlord_setup_container_name}" \
    --volume "${HOST_OVERLORD_APP_DIR}:${DOCKER_OVERLORD_APP_DIR}" \
    "${DOCKER_IMAGE_NAME}" \
    "${DOCKER_OVERLORD_DIR}/setup.sh" || \
    (echo "Setup failed... removing Overlord settings."; \
     sudo rm -rf "${HOST_OVERLORD_DIR}"; \
     die "Overlord setup failed.")

  # Copy the certificate to script directory, and set it's permission to all
  # readable, so it's easier to use (since the file is owned by root).
  sudo cp "${HOST_OVERLORD_DIR}/app/cert.pem" "${SCRIPT_DIR}/cert.pem"
  sudo chmod 644 "${SCRIPT_DIR}/cert.pem"

  echo
  echo "Setup done!"
  echo "You can find the generated certificate at ${SCRIPT_DIR}/cert.pem"
}

do_overlord_run() {
  check_docker

  local overlord_container_name="overlord"

  # stop and remove old containers
  ${DOCKER} stop "${overlord_container_name}" 2>/dev/null || true
  ${DOCKER} rm "${overlord_container_name}" 2>/dev/null || true

  if [ ! -d "${HOST_OVERLORD_DIR}" ]; then
    do_overlord_setup
  fi

  ${DOCKER} run \
    --detach \
    --restart unless-stopped \
    --name "${overlord_container_name}" \
    --volume "${HOST_OVERLORD_APP_DIR}:${DOCKER_OVERLORD_APP_DIR}" \
    --volume "${HOST_SHARED_DIR}:/mnt" \
    --publish "4455:4455" \
    --publish "4456:4456/udp" \
    --publish "${OVERLORD_HTTP_PORT}:9000" \
    --workdir "${DOCKER_OVERLORD_DIR}" \
    "${DOCKER_IMAGE_NAME}" \
    "./overlordd" -tls "app/cert.pem,app/key.pem" || \
    (echo "Removing stale container due to error ..."; \
     ${DOCKER} rm "${overlord_container_name}"; \
     die "Can't start overlord docker. Possibly wrong port binding?")
}

overlord_usage() {
  cat << __EOF__
Overlord: The Next-Gen Factory Monitor

commands:
  $0 overlord help
      Show this help message.

  $0 overlord run
      Create and start Overlord containers.

      You can change the Overlord http port (default ${OVERLORD_HTTP_PORT}) by
      assigning the OVERLORD_HTTP_PORT environment variable.
      For example:

        OVERLORD_HTTP_PORT=9090 $0 overlord run

      will bind port 9090 instead of ${OVERLORD_HTTP_PORT}.

commands for developers:
  $0 overlord setup
      Run first-time setup for Overlord. Would reset everything in app
      directory to the one in docker image.
__EOF__
}

overlord_main() {
  case "$1" in
    run)
      do_overlord_run
      ;;
    setup)
      do_overlord_setup
      ;;
    *)
      overlord_usage
      exit 1
      ;;
  esac
}

# Section for main commands
do_pull() {
  echo "Pulling Factory Server Docker image ..."
  if [[ ! -f "${DOCKER_IMAGE_FILEPATH}" ]]; then
    curl -L --fail "${PREBUILT_IMAGE_DIR_URL}/${DOCKER_IMAGE_FILENAME}" \
      -o "${DOCKER_IMAGE_FILEPATH}" || rm -f "${DOCKER_IMAGE_FILEPATH}"
    [ -f "${DOCKER_IMAGE_FILEPATH}" ] || \
      die "Failed to pull Factory Server Docker image"
  fi
  echo "Finished pulling Factory Server Docker image"

  # TODO(littlecvr): make a single, self-executable file.
  echo
  echo "All finished, please copy: "
  echo "  1. $(basename "$0") (this script)"
  echo "  2. ${DOCKER_IMAGE_FILENAME}"
  echo "to the target computer."
}

do_install() {
  check_docker

  ${DOCKER} load <"${DOCKER_IMAGE_FILEPATH}"
}

do_run() {
  check_docker

  local docker_db_dir="/var/db/factory/dome"
  local db_filename="db.sqlite3"
  local docker_log_dir="/var/log/dome"
  local host_log_dir="${HOST_DOME_DIR}/log"
  local uwsgi_container_name="dome_uwsgi"
  local nginx_container_name="dome_nginx"

  # stop and remove old containers
  ${DOCKER} stop "${uwsgi_container_name}" 2>/dev/null || true
  ${DOCKER} rm "${uwsgi_container_name}" 2>/dev/null || true
  ${DOCKER} stop "${nginx_container_name}" 2>/dev/null || true
  ${DOCKER} rm "${nginx_container_name}" 2>/dev/null || true

  # make sure database file exists or mounting volume will fail
  if [[ ! -f "${HOST_DOME_DIR}/${db_filename}" ]]; then
    echo "Creating docker shared folder (${HOST_DOME_DIR}),"
    echo "and database file, you'll be asked for root permission ..."
    ensure_dir "${HOST_DOME_DIR}"
    sudo touch "${HOST_DOME_DIR}/${db_filename}"
    ensure_dir_acl "${HOST_SHARED_DIR}"
  fi

  # Migrate the database if needed (won't remove any data if the database
  # already exists, but will apply the schema changes). This command may ask
  # user questions and need the user input, so make it interactive.
  ${DOCKER} run \
    --rm \
    --interactive \
    --tty \
    --volume "${HOST_DOME_DIR}/${db_filename}:${docker_db_dir}/${db_filename}" \
    --volume "${host_log_dir}:${docker_log_dir}" \
    --workdir "${DOCKER_DOME_DIR}" \
    "${DOCKER_IMAGE_NAME}" \
    python manage.py migrate

  # Clear all temporary uploaded file records. These files were uploaded to
  # container but not in a volume, so they will be gone once the container has
  # been removed.
  ${DOCKER} run \
    --rm \
    --volume "${HOST_DOME_DIR}/${db_filename}:${docker_db_dir}/${db_filename}" \
    --volume "${host_log_dir}:${docker_log_dir}" \
    --workdir "${DOCKER_DOME_DIR}" \
    "${DOCKER_IMAGE_NAME}" \
    python manage.py shell --command \
    "import backend; backend.models.TemporaryUploadedFile.objects.all().delete()"

  # start uwsgi, the bridge between django and nginx
  # Note 'docker' currently reads from '/var/run/docker.sock', which does not
  # follow FHS 3.0
  ${DOCKER} run \
    --detach \
    --restart unless-stopped \
    --name "${uwsgi_container_name}" \
    --volume /var/run/docker.sock:/var/run/docker.sock \
    --volume /run \
    --volume "${HOST_DOME_DIR}/${db_filename}:${docker_db_dir}/${db_filename}" \
    --volume "${host_log_dir}:${docker_log_dir}" \
    --volume "${HOST_UMPIRE_DIR}:${DOCKER_UMPIRE_DIR_IN_DOME}" \
    --workdir "${DOCKER_DOME_DIR}" \
    "${DOCKER_IMAGE_NAME}" \
    uwsgi --ini uwsgi.ini

  # start nginx
  ${DOCKER} run \
    --detach \
    --restart unless-stopped \
    --name "${nginx_container_name}" \
    --volumes-from "${uwsgi_container_name}" \
    --publish "${DOME_PORT}:80" \
    --workdir "${DOCKER_DOME_DIR}" \
    "${DOCKER_IMAGE_NAME}" \
    nginx -g "daemon off;"

  echo
  echo "Dome is running!"
  echo "Open the browser to http://localhost:${DOME_PORT}/ and enjoy!"
}

do_build_dome_deps() {
  check_docker

  local builder_output_file="$1"
  local builder_workdir="/usr/src/app"
  local builder_dockerfile="${DOME_DIR}/docker/Dockerfile.builder"
  local builder_container_name="dome_builder"
  local builder_image_name="cros/dome-builder"

  # build the dome builder image
  ${DOCKER} build \
    --file "${builder_dockerfile}" \
    --tag "${builder_image_name}" \
    --build-arg workdir="${builder_workdir}" \
    --build-arg output_file="${builder_output_file}" \
    "${DOME_DIR}"

  # copy the builder's output from container to host
  mkdir -p "${BUILD_DIR}"
  ${DOCKER} create --name "${builder_container_name}" "${builder_image_name}"
  ${DOCKER} cp \
    "${builder_container_name}:${builder_workdir}/${builder_output_file}" \
    "${BUILD_DIR}"
  ${DOCKER} rm "${builder_container_name}"
}

do_build_overlord() {
  # We're using alpine for factory_server docker image, which is using musl
  # libc instead of standard glibc, causing overlord compiled on host/chroot
  # not able to run inside the docker image. So we have to compile it inside
  # golang:alpine too.
  check_docker

  local builder_output_file="$1"
  local builder_workdir="/tmp/build"
  local builder_dockerfile="${SCRIPT_DIR}/Dockerfile.overlord"
  local builder_container_name="overlord_builder"
  local builder_image_name="cros/overlord-builder"

  # build the overlord builder image
  ${DOCKER} build \
    --file "${builder_dockerfile}" \
    --tag "${builder_image_name}" \
    --build-arg workdir="${builder_workdir}" \
    --build-arg output_file="${builder_output_file}" \
    "${FACTORY_DIR}"

  # copy the builder's output from container to host
  mkdir -p "${BUILD_DIR}"
  ${DOCKER} create --name "${builder_container_name}" "${builder_image_name}"
  ${DOCKER} cp \
    "${builder_container_name}:${builder_workdir}/${builder_output_file}" \
    "${BUILD_DIR}"
  ${DOCKER} rm "${builder_container_name}"
}

do_build() {
  check_docker

  local dome_builder_output_file="frontend.tar"
  local overlord_output_file="overlord.tar.gz"

  do_build_dome_deps "${dome_builder_output_file}"
  do_build_overlord "${overlord_output_file}"

  local dockerfile="${SCRIPT_DIR}/Dockerfile"

  fetch_resource "${BUILD_DIR}/docker.tgz" \
    "${RESOURCE_DOCKER_URL}" "${RESOURCE_DOCKER_SHA1}"

  # need to make sure we're using the same version of docker inside the container
  ${DOCKER} build \
    --file "${dockerfile}" \
    --tag "${DOCKER_IMAGE_NAME}" \
    --build-arg dome_dir="${DOCKER_DOME_DIR}" \
    --build-arg server_dir="${DOCKER_BASE_DIR}" \
    --build-arg instalog_dir="${DOCKER_INSTALOG_DIR}" \
    --build-arg umpire_dir_in_dome="${DOCKER_UMPIRE_DIR_IN_DOME}" \
    --build-arg dome_builder_output_file="${dome_builder_output_file}" \
    --build-arg overlord_output_file="${overlord_output_file}" \
    "${FACTORY_DIR}"

  echo "${DOCKER_IMAGE_NAME} image successfully built."
}

# This function must run in ${FACTORY_DIR}.
do_update_docker_image_version() {
  local script_file="$1"
  local changes_file="$2"

  # Check local modification.
  if [ -n "$(git status --porcelain)" ]; then
    die "Your have uncommitted or untracked changes.  " \
        "To publish you have to build without local modification."
  fi

  # Check if the head is already on remotes/cros/master.
  local head="$(git rev-parse HEAD 2>/dev/null)"
  local upstream="$(git merge-base remotes/m/master "${head}")"

  if [ "${head}" != "${upstream}" ] || [ -z "${head}" ]; then
    die "Your latest commit was not merged to upstream (remotes/m/master)." \
        "To publish you have to build without local commits."
  fi

  local source_list=(
      setup/Dockerfile
      setup/Dockerfile.overlord
      setup/cros_docker.sh
      py/dome
      py/instalog
      py/umpire
      go/src
  )

  git log --oneline ${DOCKER_IMAGE_GITHASH}.. "${source_list[@]}" \
    | grep -v " ${COMMIT_SUBJECT} " >"${changes_file}"

  if [ -s "${changes_file}" ]; then
    echo "Server related changes since last build (${DOCKER_IMAGE_BUILD}):"
    cat "${changes_file}"
    echo "---"
  else
    # TODO(hungte) Make an option to allow forced publishing.
    die "No server related changes since last publish."
  fi

  local branch_name="$(git rev-parse --abbrev-ref HEAD)"
  local new_timestamp="$(date '+%Y%m%d%H%M%S')"
  if [ "${branch_name}" = "HEAD" ]; then
    # We are on a detached HEAD - should start a new branch to work on so
    # do_commit_docker_image_version can create a new commit.
    # This is required before making any changes to ${script_file}.
    repo start "cros_docker_${new_timestamp}" .
  fi

  echo "Update publish information in $0..."
  sed -i "s/${DOCKER_IMAGE_GITHASH}/${head}/;
          s/${DOCKER_IMAGE_TIMESTAMP}/${new_timestamp}/" "${script_file}"
}

do_reload_docker_image_info() {
  local script_file="$1"
  DOCKER_IMAGE_GITHASH="$(sed -n 's/^DOCKER_IMAGE_GITHASH="\(.*\)"/\1/p' \
                          "${script_file}")"
  DOCKER_IMAGE_TIMESTAMP="$(sed -n 's/^DOCKER_IMAGE_TIMESTAMP="\(.*\)"/\1/p' \
                            "${script_file}")"
  set_docker_image_info
}

do_commit_docker_image_release()
{
  git commit -a -s -m \
    "${COMMIT_SUBJECT} ${DOCKER_IMAGE_TIMESTAMP}.

A new release of cros_docker image on ${DOCKER_IMAGE_TIMESTAMP},
built from source using hash ${DOCKER_IMAGE_GITHASH}.
Published as ${DOCKER_IMAGE_FILENAME}.

Major changes:
$(cat "${CHANGES_FILE}")

BUG=chromium:679609
TEST=None"
  git show HEAD
  echo "Uploading to gerrit..."
  repo upload --cbr --no-verify .
}

do_publish() {
  check_gsutil

  local script_file="$(realpath "$0")"
  CHANGES_FILE="$(mktemp)"
  TEMP_OBJECTS=("${CHANGES_FILE}" "${TEMP_OBJECTS[@]}")
  (cd "${FACTORY_DIR}" && \
    do_update_docker_image_version "${script_file}" "${CHANGES_FILE}") ||
    die "Failed updating docker image version."

  do_reload_docker_image_info "${script_file}"

  local factory_server_image_url="${GSUTIL_BUCKET}/${DOCKER_IMAGE_FILENAME}"
  if gsutil stat "${factory_server_image_url}" >/dev/null 2>&1; then
    die "${DOCKER_IMAGE_FILENAME} is already on chromeos-localmirror"
  fi

  do_build  # make sure we have the newest image

  local temp_dir="$(mktemp -d)"
  TEMP_OBJECTS=("${temp_dir}" "${TEMP_OBJECTS[@]}")

  (cd "${temp_dir}"; do_save)
  upload_to_localmirror "${temp_dir}/${DOCKER_IMAGE_FILENAME}" \
    "${factory_server_image_url}"

  (cd "${FACTORY_DIR}" && do_commit_docker_image_release)
}

do_save() {
  check_docker
  check_xz

  echo "Saving Factory Server docker image to ${PWD}/${DOCKER_IMAGE_FILENAME} ..."
  ${DOCKER} save "${DOCKER_IMAGE_NAME}" | ${XZ} >"${DOCKER_IMAGE_FILENAME}"
  echo "Umpire docker image saved to ${PWD}/${DOCKER_IMAGE_FILENAME}"
}

do_update() {
  local script_file="$(realpath "$0")"
  local temp_file="$(mktemp)"
  local prefix="sudo"
  TEMP_OBJECTS=("${temp_file}" "${TEMP_OBJECTS[@]}")

  curl -L --fail "${RESOURCE_CROS_DOCKER_URL}" | base64 -d >"${temp_file}"
  [ -s "${temp_file}" ] || die "Failed to download deployment script."
  chmod +x "${temp_file}"
  "${temp_file}" version || die "Failed to verify deployment script."
  echo "Successfully downloaded latest deployment script."
  if [ -w "${script_file}" ]; then
    # No need to run sudo.
    prefix=
  fi

  # Can't keep running anything in the script.
  exec ${prefix} mv -f "${temp_file}" "${script_file}"
}

usage() {
  cat << __EOF__
Chrome OS Factory Server Deployment Script

commands:
  $0 help
      Show this help message.

  $0 update
      Update deployment script itself.

  $0 pull
      Pull factory server docker images.

  $0 install
      Load factory server docker images.

  $0 version
      Print target factory server docker image file version.

  $0 run
      Create and start Dome containers.

      You can change the listening port (default ${DOME_PORT}) by assigning the
      DOME_PORT environment variable. For example:

        DOME_PORT=1234 $0 run

      will bind port 1234 instead of ${DOME_PORT}.

common use case:
  - Run "$0 pull" to download docker images, and copy files listed on screen
    to the target computer.
  - Run "$0 install" on the target computer to load docker images.
  - Run "$0 run" to start Dome.

commands for developers:
  $0 build
      Build factory server docker image.

  $0 publish
      Build and publish factory server docker image to chromeos-localmirror.

  $0 save
      Save factory server docker image to the current working directory.

  $0 umpire [subcommand]
      Commands for Umpire, see "$0 umpire help" for detail.

  $0 overlord [subcommand]
      Commands for Overlord, see "$0 overlord help" for detail.
__EOF__
}

main() {
  case "$1" in
    pull)
      do_pull
      ;;
    install)
      do_install
      ;;
    run)
      do_run
      ;;
    build)
      do_build
      ;;
    publish)
      do_publish
      ;;
    save)
      do_save
      ;;
    update)
      do_update
      ;;
    version)
      echo "Chrome OS Factory Server: ${DOCKER_IMAGE_VERSION}"
      ;;
    umpire)
      shift
      umpire_main "$@"
      ;;
    overlord)
      shift
      overlord_main "$@"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
