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

is_macosx() {
  [ "$(uname -s)" = "Darwin" ]
}

realpath() {
  # Try to find "realpath" in a portable way.
  if type python2 >/dev/null 2>&1; then
    python2 -c 'import sys; import os; print os.path.realpath(sys.argv[1])' "$1"
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

run_in_factory() {
  (cd "${FACTORY_DIR}"; "$@")
}

# Base directories
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
FACTORY_DIR="$(dirname "${SCRIPT_DIR}")"
UMPIRE_DIR="${FACTORY_DIR}/py/umpire"
DOME_DIR="${FACTORY_DIR}/py/dome"
OVERLORD_DIR="${FACTORY_DIR}/go/src/overlord"
BUILD_DIR="${FACTORY_DIR}/build/docker"

# Platform specific directory defaults.
if is_macosx; then
  DEFAULT_HOST_SHARED_DIR="${HOME}/cros_docker"
  # osxfs needs the folder to be owned by current user.
  SHARED_WITH_USER_ACL=true
  # The /etc/localtime is not available on recent Docker builds.
  DEFAULT_HOST_LOCALTIME_PATH=""
else
  DEFAULT_HOST_SHARED_DIR="/cros_docker"
  SHARED_WITH_USER_ACL=false
  DEFAULT_HOST_LOCALTIME_PATH=/etc/localtime
fi

# Directories on host that would be mounted to docker
# This would be overridden in integration tests.
: "${HOST_SHARED_DIR:="${DEFAULT_HOST_SHARED_DIR}"}"
: "${HOST_LOCALTIME_PATH:="${DEFAULT_HOST_LOCALTIME_PATH}"}"
HOST_DOME_DIR="${HOST_SHARED_DIR}/dome"
HOST_TFTP_DIR="${HOST_SHARED_DIR}/tftp"
HOST_UMPIRE_DIR="${HOST_SHARED_DIR}/umpire"
HOST_OVERLORD_DIR="${HOST_SHARED_DIR}/overlord"
HOST_OVERLORD_CONFIG_DIR="${HOST_OVERLORD_DIR}/config"
HOST_GOOFY_DIR="${HOST_SHARED_DIR}/goofy"

# Shared temporary volume between Dome and Umpire.
HOST_SHARED_TMP_VOLUME="cros-docker-shared-tmp-vol"

# Publish tools
PREBUILT_IMAGE_SITE="https://storage.googleapis.com"
PREBUILT_IMAGE_DIR_URL="${PREBUILT_IMAGE_SITE}/chromeos-localmirror/distfiles"
GSUTIL_BUCKET="gs://chromeos-localmirror/distfiles"
COMMIT_SUBJECT="setup: Publish cros_docker image version"

# Remote resources
RESOURCE_DOCKER_URL="${PREBUILT_IMAGE_DIR_URL}/docker-${DOCKER_VERSION}.tgz"
RESOURCE_DOCKER_SHA1="17239c2d84413affa68bbe444c3402905e863d1f"
RESOURCE_CROS_DOCKER_URL="https://chromium.googlesource.com/chromiumos/platform/factory/+/master/setup/cros_docker.sh?format=TEXT"
RESOURCE_PIXZ_URL="${PREBUILT_IMAGE_DIR_URL}/pixz-1.0.6-amd64-static.tbz2"
RESOURCE_PIXZ_SHA1="3bdf7473df19f2d089f2a9b055c18a4f7f1409e5"

# Directories inside docker
DOCKER_BASE_DIR="/usr/local/factory"
DOCKER_DOME_DIR="${DOCKER_BASE_DIR}/py/dome"
DOCKER_DOME_FRONTEND_DIR="${DOCKER_DOME_DIR}/frontend"
DOCKER_UMPIRE_DIR="${DOCKER_BASE_DIR}/py/umpire"
DOCKER_INSTALOG_DIR="${DOCKER_BASE_DIR}/py/instalog"

DOCKER_OVERLORD_DIR="${DOCKER_BASE_DIR}/bin/overlord"
DOCKER_OVERLORD_CONFIG_DIR="${DOCKER_OVERLORD_DIR}/config"

DOCKER_SHARED_TMP_DIR="/tmp/shared"

# Umpire's db directory mount point in Dome
DOCKER_UMPIRE_DIR_IN_DOME="/var/db/factory/umpire"

# TFTP root mount point in Dome
DOCKER_TFTP_DIR_IN_DOME="/var/tftp"

# DOCKER_IMAGE_{GITHASH,TIMESTAMP} will be updated when you publish.
DOCKER_IMAGE_GITHASH="72994a8327fbdd368e1d3003611127e8e2dd5788"
DOCKER_IMAGE_TIMESTAMP="20190916140050"
DOCKER_IMAGE_NAME="cros/factory_server"

if [ -n "${HOST_LOCALTIME_PATH}" ]; then
  DOCKER_LOCALTIME_VOLUME="--volume ${HOST_LOCALTIME_PATH}:/etc/localtime:ro"
else
  DOCKER_LOCALTIME_VOLUME=""
fi

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
: "${PROJECT:="$(cat "${HOST_UMPIRE_DIR}/.default_project" 2>/dev/null)"}"
: "${PROJECT:="default"}"
: "${UMPIRE_CONTAINER_NAME:="umpire_${PROJECT}"}"
: "${UMPIRE_CONTAINER_DIR:="${HOST_UMPIRE_DIR}/${PROJECT}"}"
: "${UMPIRE_PORT:="8080"}"  # base port for Umpire
: "${DOME_PORT:="8000"}"  # port to access Dome
: "${DOME_DEV_PORT:="18000"}"  # port to access Dome dev server
: "${GOOFY_PORT:="4012"}"  # port to access Goofy
: "${OVERLORD_HTTP_PORT:="9000"}"  # port to access Overlord
: "${OVERLORD_LAN_DISC_IFACE:=""}"  # The network interface that Overlord LAN
                                    # discovery should be run on.

DOME_UWSGI_CONTAINER_NAME="dome_uwsgi"
DOME_NGINX_CONTAINER_NAME="dome_nginx"

DOME_BUILDER_IMAGE_NAME="cros/dome-builder"

DOME_DEV_FRONTEND_CONTAINER_NAME="dome_dev_frontend"
DOME_DEV_DJANGO_CONTAINER_NAME="dome_dev_django"
DOME_DEV_NGINX_CONTAINER_NAME="dome_dev_nginx"
DOME_DEV_DOCKER_NETWORK_NAME="dome_dev_network"

ensure_dir() {
  local dir="$1"
  if [ ! -d "${dir}" ]; then
    sudo mkdir -p "${dir}"
  fi
}

ensure_dir_acl() {
  local dir="$1"
  if "${SHARED_WITH_USER_ACL}"; then
    sudo chown -R "$(id -u)" "${dir}"
    sudo chgrp -R "$(id -g)" "${dir}"
  fi
}

check_file_sha1() {
  local file="$1"
  local sha1="$2"
  [[ -f "${file}" ]] && echo "${sha1} ${file}" | sha1sum -c
}

fetch_resource() {
  local local_name="$1"
  local url="$2"
  local sha1="$3"

  if ! check_file_sha1 "${local_name}" "${sha1}"; then
    rm -f "${local_name}"
    curl -L --fail "${url}" -o "${local_name}" || rm -f "${local_name}"
    if ! check_file_sha1 "${local_name}" "${sha1}"; then
      die "Error when fetching resource ${url}"
    fi
  fi
}

check_git_status() {
  [ -z "$(run_in_factory git status --porcelain)" ]
}

get_git_hash() {
  run_in_factory git rev-parse HEAD
}

stop_and_remove_container() {
  ${DOCKER} stop "$1" 2>/dev/null || true
  ${DOCKER} rm "$1" 2>/dev/null || true
}

# Section for Umpire subcommand
do_umpire_run() {
  check_docker

  # Separate umpire db for each container.
  local docker_db_dir="/var/db/factory/umpire"

  ensure_dir "${HOST_SHARED_DIR}"
  ensure_dir "${UMPIRE_CONTAINER_DIR}"
  ensure_dir_acl "${HOST_SHARED_DIR}"

  stop_and_remove_container "${UMPIRE_CONTAINER_NAME}"

  echo "Starting Umpire container ..."

  local p1=${UMPIRE_PORT}        # Imaging & Shopfloor
  local p2=$((UMPIRE_PORT + 2))  # CLI RPC
  local p3=$((UMPIRE_PORT + 4))  # Rsync
  local p4=$((UMPIRE_PORT + 6))  # Instalog output_pull_socket plugin
  local p5=$((UMPIRE_PORT + 8))  # Instalog customized output plugin

  local umpire_base_port=8080
  local umpire_cli_port=$((umpire_base_port + 2))
  local umpire_rsync_port=$((umpire_base_port + 4))
  local umpire_instalog_pull_socket_port=$((umpire_base_port + 6))
  local umpire_instalog_customized_output_port=$((umpire_base_port + 8))

  ${DOCKER} run \
    --detach \
    --restart unless-stopped \
    --name "${UMPIRE_CONTAINER_NAME}" \
    --tmpfs "/run:rw,size=16384k" \
    ${DOCKER_LOCALTIME_VOLUME} \
    --volume "${HOST_SHARED_DIR}:/mnt" \
    --volume "${UMPIRE_CONTAINER_DIR}:${docker_db_dir}" \
    --volume "${HOST_SHARED_TMP_VOLUME}:${DOCKER_SHARED_TMP_DIR}" \
    --publish "${p1}:${umpire_base_port}" \
    --publish "${p2}:${umpire_cli_port}" \
    --publish "${p3}:${umpire_rsync_port}" \
    --publish "${p4}:${umpire_instalog_pull_socket_port}" \
    --publish "${p5}:${umpire_instalog_customized_output_port}" \
    --env "UMPIRE_PROJECT_NAME=${PROJECT}" \
    --privileged \
    "${DOCKER_IMAGE_NAME}" \
    "${DOCKER_BASE_DIR}/bin/umpired" || \
    (echo "Removing stale container due to error ..."; \
     ${DOCKER} rm "${UMPIRE_CONTAINER_NAME}"; \
     die "Can't start umpire docker. Possibly wrong port binding?")

  echo "done"
  echo
  echo "*** NOTE ***"
  echo "- Host directory ${HOST_SHARED_DIR} is mounted" \
       "under /mnt in the container."
  echo "- Host directory ${UMPIRE_CONTAINER_DIR} is mounted" \
       "under ${docker_db_dir} in the container."
  echo "- Umpire service ports is mapped to the local machine."
}

do_umpire_destroy() {
  check_docker

  echo -n "Deleting ${UMPIRE_CONTAINER_NAME} container ... "
  ${DOCKER} stop "${UMPIRE_CONTAINER_NAME}" >/dev/null 2>&1 || true
  ${DOCKER} rm "${UMPIRE_CONTAINER_NAME}" >/dev/null 2>&1 || true
  echo "done"
}

check_container_status() {
  local container_name="$1"
  if ! ${DOCKER} ps --format "{{.Names}} {{.Status}}" \
    | grep -q "${container_name} Up "; then
    die "${container_name} container is not running"
  fi
}

do_umpire_shell() {
  check_docker
  check_container_status "${UMPIRE_CONTAINER_NAME}"

  ${DOCKER} exec -it "${UMPIRE_CONTAINER_NAME}" sh
}

do_umpire_test() {
  check_docker

  do_build

  local umpire_tester_image_name="cros/umpire_tester"
  local dockerfile="${UMPIRE_DIR}/server/e2e_test/Dockerfile"

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
    ${DOCKER_LOCALTIME_VOLUME} \
    --volume "${temp_dir}:${temp_dir}" \
    --volume /run/docker.sock:/run/docker.sock \
    --volume /run \
    --env "TMPDIR=${temp_dir}" \
    --env "LOG_LEVEL=${LOG_LEVEL}" \
    "${umpire_tester_image_name}" \
    "${DOCKER_UMPIRE_DIR}/server/e2e_test/e2e_test.py" "$@"

  touch "${UMPIRE_DIR}/.tests-passed"
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

goofy_usage() {
  cat << __EOF__
Run the test harness and UI "Goofy" in Docker environment.

Most subcommands support an optional "CROS_TEST_DOCKER_IMAGE" argument, which is
the Docker image repository name when you have imported a Chromium OS image
using '${SCRIPT_DIR}/image_tool docker -i IMAGE'. If you have only one image
installed, that image will be selected automatically.

commands:
  $0 goofy help
      Show this help message.

  $0 goofy try [CROS_TEST_DOCKER_IMAGE] [-- [arg1 [arg2 ...]]]
      Quickly run the Goofy from source tree.

      This command will try to run Goofy directly using your local source tree.
      You have to first build goofy.js and locale folders manually, by running
      following commands inside chroot:

        make
        make po

      Then, you can start Goofy by 'try' command, and access to the web UI in
      GOOFY_PORT (default ${GOOFY_PORT}).  For example:

        GOOFY_PORT=1234 $0 goofy try

  $0 goofy shell [CROS_TEST_DOCKER_IMAGE]
      Starts a shell to install and run Goofy manually.

      Unlike 'try' command, the 'shell' does not need source tree. Instead it
      will allocate an empty folder in ${HOST_GOOFY_DIR} for you to install
      a full Goofy toolkit installer, and then Goofy from there manually.
__EOF__
}

# Run Goofy inside Docker.
goofy_main() {
  local try=false
  case "$1" in
    shell)
      shift
      ;;
    try)
      try=true
      shift
      ;;
    *)
      goofy_usage
      exit 1
      ;;
  esac

  check_docker

  # Decide CROS_TEST_DOCKER_IMAGE
  local name=""
  if [ "$#" -gt 0 -a "$1" != "--" ]; then
    name="$1"
    shift
  else
    # Try to find existing images.
    local all_images="$( \
      ${DOCKER} images "cros/*_test"  --format "{{.Repository}}" | uniq)"
    case "$(echo "${all_images}" | wc -w)" in
      1)
        name="${all_images}"
        ;;
      0)
        ;;
      *)
        die "Multiple images found, you have to specify one: " ${all_images}
        ;;
    esac
  fi
  if [ "$#" -gt 0 ]; then
    if [ "$1" != "--" ]; then
      goofy_usage
      exit 1
    fi
    shift
  fi
  # Normalize name and check if the image exists.
  if [ -z "${name}" ]; then
    die "Need Docker image from Chromium OS test image (image_tool docker)."
  elif [ "${name##*/}" = "${name}" ]; then
    name="cros/${name}"
  fi
  if [ -z "$(${DOCKER} images "${name}" --format '{{.Repository}}')" ]; then
    die "Docker image does not exist: ${name}"
  fi

  ensure_dir "${HOST_GOOFY_DIR}/var_factory"
  ensure_dir_acl "${HOST_SHARED_DIR}"

  local locale_dir="${FACTORY_DIR}/build/locale"
  local commands=()

  if "${try}"; then
    if [ ! -e "${locale_dir}" ]; then
      die "Please do 'make po' in chroot first."
    fi
    if [ ! -e "${FACTORY_DIR}/py/goofy/static/js/goofy.js" ]; then
      die "Please do 'make default' in chroot first."
    fi
    # TODO(hungte) Support board overlay.
    commands=(
        "--volume" "${FACTORY_DIR}:/usr/local/factory"
        "--volume" "${FACTORY_DIR}/build/locale:/usr/local/factory/locale"
        "--env" "PYTHONDONTWRITEBYTECODE=1"
        "${name}" "/usr/local/factory/bin/goofy_docker" "${@}")
    echo ">> Starting Docker image ${name} in http://localhost:${GOOFY_PORT} .."
  else
    ensure_dir "${HOST_GOOFY_DIR}/local_factory"
    if [ ! -e "${HOST_GOOFY_DIR}/local_factory/TOOLKIT_VERSION" ]; then
      echo "You have to first manually install a toolkit."
      echo "Copy the install_factory_toolkit.run to ${HOST_SHARED_DIR}"
      echo " and then execute /mnt/install_factory_toolkit.run inside docker."
    fi
    echo "To start Goofy, run '${DOCKER_BASE_DIR}/bin/goofy_docker'."
    commands=(
        "--volume" "${HOST_GOOFY_DIR}/local_factory:/usr/local/factory"
        "${name}" "bash")
  fi

  ${DOCKER} run \
    --interactive \
    --tty \
    --rm \
    --name "goofy_${name##*/}" \
    --volume "${HOST_SHARED_DIR}:/mnt" \
    --volume "${HOST_GOOFY_DIR}/var_factory:/var/factory" \
    --publish "${GOOFY_PORT}:4012" \
    --tmpfs "/run:rw,size=16384k" \
    --tmpfs /var/log \
    "${commands[@]}"
}

# Section for Overlord subcommand
do_overlord_setup() {
  check_docker

  local overlord_setup_container_name="overlord_setup"

  echo "Doing setup for Overlord, you'll be asked for root permission ..."
  sudo rm -rf "${HOST_OVERLORD_DIR}"
  ensure_dir "${HOST_OVERLORD_CONFIG_DIR}"
  ensure_dir_acl "${HOST_SHARED_DIR}"

  echo "Running setup script ..."
  echo

  ${DOCKER} run \
    --interactive \
    --tty \
    --rm \
    --name "${overlord_setup_container_name}" \
    --volume "${HOST_OVERLORD_CONFIG_DIR}:${DOCKER_OVERLORD_CONFIG_DIR}" \
    "${DOCKER_IMAGE_NAME}" \
    "${DOCKER_OVERLORD_DIR}/setup.sh" || \
    (echo "Setup failed... removing Overlord settings."; \
     sudo rm -rf "${HOST_OVERLORD_DIR}"; \
     die "Overlord setup failed.")

  # Copy the certificate to script directory, and set it's permission to all
  # readable, so it's easier to use (since the file is owned by root).
  sudo cp "${HOST_OVERLORD_DIR}/config/cert.pem" "${SCRIPT_DIR}/cert.pem"
  sudo chmod 644 "${SCRIPT_DIR}/cert.pem"

  echo
  echo "Setup done!"
  echo "You can find the generated certificate at ${SCRIPT_DIR}/cert.pem"
}

do_overlord_run() {
  check_docker

  local overlord_container_name="overlord"
  local overlord_lan_disc_container_name="overlord_lan_disc"

  stop_and_remove_container "${overlord_container_name}"
  stop_and_remove_container "${overlord_lan_disc_container_name}"

  if [ ! -d "${HOST_OVERLORD_DIR}" ]; then
    do_overlord_setup
  fi

  ${DOCKER} run \
    --detach \
    --restart unless-stopped \
    --name "${overlord_container_name}" \
    --volume "${HOST_OVERLORD_CONFIG_DIR}:${DOCKER_OVERLORD_CONFIG_DIR}" \
    --volume "${HOST_SHARED_DIR}:/mnt" \
    --publish "4455:4455" \
    --publish "${OVERLORD_HTTP_PORT}:9000" \
    --workdir "${DOCKER_OVERLORD_DIR}" \
    "${DOCKER_IMAGE_NAME}" \
    "./overlordd" -tls "config/cert.pem,config/key.pem" \
    -htpasswd-path "config/overlord.htpasswd" -no-lan-disc || \
    (echo "Removing stale container due to error ..."; \
     ${DOCKER} rm "${overlord_container_name}"; \
     die "Can't start overlord docker. Possibly wrong port binding?")

  # The Overlord LAN discovery need to be run with --net host.
  ${DOCKER} run \
    --detach \
    --restart unless-stopped \
    --name "${overlord_lan_disc_container_name}" \
    --workdir "${DOCKER_OVERLORD_DIR}" \
    --net host \
    "${DOCKER_IMAGE_NAME}" \
    "./overlord_lan_disc" -lan-disc-iface "${OVERLORD_LAN_DISC_IFACE}"|| \
    (echo "Removing stale container due to error ..."; \
     ${DOCKER} rm "${overlord_lan_disc_container_name}"; \
     die "Can't start overlord lan discovery docker.")
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
      Run first-time setup for Overlord. Would reset everything in config
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

do_dev_run() {
  check_docker

  do_build

  local docker_db_dir="/var/db/factory/dome"
  local db_filename="db.sqlite3"
  local docker_log_dir="/var/log/dome"
  local host_log_dir="${HOST_DOME_DIR}/log"
  local builder_container_name="dome_builder"

  # stop and remove old containers
  do_dev_destroy

  do_prepare_dome

  echo "Copying node_modules into host directory ..."
  ${DOCKER} create --name "${builder_container_name}" \
    "${DOME_BUILDER_IMAGE_NAME}"
  ${DOCKER} cp \
    "${builder_container_name}:${DOCKER_DOME_FRONTEND_DIR}/node_modules" \
    "${DOME_DIR}/frontend"
  ${DOCKER} rm "${builder_container_name}"

  ${DOCKER} network create "${DOME_DEV_DOCKER_NETWORK_NAME}"

  # Start dev server for frontend code.
  ${DOCKER} run \
    --detach \
    --restart unless-stopped \
    --name "${DOME_DEV_FRONTEND_CONTAINER_NAME}" \
    --network "${DOME_DEV_DOCKER_NETWORK_NAME}" \
    --volume "${DOME_DIR}:${DOCKER_DOME_DIR}" \
    ${DOCKER_LOCALTIME_VOLUME} \
    --workdir "${DOCKER_DOME_FRONTEND_DIR}" \
    "${DOME_BUILDER_IMAGE_NAME}" \
    npm run dev

  # start django development server.
  ${DOCKER} run \
    --detach \
    --restart unless-stopped \
    --name "${DOME_DEV_DJANGO_CONTAINER_NAME}" \
    --network "${DOME_DEV_DOCKER_NETWORK_NAME}" \
    --volume /var/run/docker.sock:/var/run/docker.sock \
    --env HOST_SHARED_DIR="${HOST_SHARED_DIR}" \
    --env HOST_UMPIRE_DIR="${HOST_UMPIRE_DIR}" \
    --env HOST_TFTP_DIR="${HOST_TFTP_DIR}" \
    --env HOST_LOCALTIME_PATH="${HOST_LOCALTIME_PATH}" \
    --env DOME_DEV_SERVER="1" \
    --env PYTHONDONTWRITEBYTECODE="1" \
    --volume /run \
    --volume "${DOME_DIR}:${DOCKER_DOME_DIR}" \
    --volume "${HOST_DOME_DIR}/${db_filename}:${docker_db_dir}/${db_filename}" \
    --volume "${host_log_dir}:${docker_log_dir}" \
    --volume "${HOST_TFTP_DIR}:${DOCKER_TFTP_DIR_IN_DOME}" \
    --volume "${HOST_UMPIRE_DIR}:${DOCKER_UMPIRE_DIR_IN_DOME}" \
    --volume "${HOST_SHARED_TMP_VOLUME}:${DOCKER_SHARED_TMP_DIR}" \
    ${DOCKER_LOCALTIME_VOLUME} \
    --workdir "${DOCKER_DOME_DIR}" \
    "${DOCKER_IMAGE_NAME}" \
    python2 manage.py runserver 0:8080

  # start nginx
  ${DOCKER} run \
    --detach \
    --restart unless-stopped \
    --name "${DOME_DEV_NGINX_CONTAINER_NAME}" \
    --network "${DOME_DEV_DOCKER_NETWORK_NAME}" \
    --volumes-from "${DOME_DEV_DJANGO_CONTAINER_NAME}" \
    --publish "127.0.0.1:${DOME_DEV_PORT}:80" \
    "${DOCKER_IMAGE_NAME}" \
    nginx -g "daemon off;" -c "${DOCKER_DOME_DIR}/nginx.dev.conf"

  echo
  echo "Dome Dev server is running!"
  echo "Open the browser to http://localhost:${DOME_DEV_PORT}/ and enjoy!"
}

do_dev_destroy() {
  check_docker

  stop_and_remove_container "${DOME_DEV_FRONTEND_CONTAINER_NAME}"
  stop_and_remove_container "${DOME_DEV_DJANGO_CONTAINER_NAME}"
  stop_and_remove_container "${DOME_DEV_NGINX_CONTAINER_NAME}"
  ${DOCKER} network rm "${DOME_DEV_DOCKER_NETWORK_NAME}" 2>/dev/null || true
}

dev_usage() {
  cat << __EOF__
Dome development server.

The server would use py/dome/{frontend,backend} on host directly, and
automatically reload when file changed.

commands:
  $0 dev help
      Show this help message.

  $0 dev run
      Create and start development server for Dome.

      You can change the listening port (default ${DOME_DEV_PORT}) by assigning
      the DOME_DEV_PORT environment variable. For example:

        DOME_DEV_PORT=1234 $0 dev run

      will bind port 1234 instead of ${DOME_DEV_PORT}.

  $0 dev destroy
      Stop and remove the development server.
__EOF__
}

dev_main() {
  case "$1" in
    "")
      do_dev_run
      ;;
    run)
      do_dev_run
      ;;
    destroy)
      do_dev_destroy
      ;;
    *)
      dev_usage
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

do_prepare_dome() {
  check_docker

  local docker_db_dir="/var/db/factory/dome"
  local db_filename="db.sqlite3"
  local docker_log_dir="/var/log/dome"
  local host_log_dir="${HOST_DOME_DIR}/log"

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
    python2 manage.py migrate

  # Clear all temporary uploaded file records. These files were uploaded to
  # container but not in a volume, so they will be gone once the container has
  # been removed.
  ${DOCKER} run \
    --rm \
    --volume "${HOST_DOME_DIR}/${db_filename}:${docker_db_dir}/${db_filename}" \
    --volume "${host_log_dir}:${docker_log_dir}" \
    --workdir "${DOCKER_DOME_DIR}" \
    "${DOCKER_IMAGE_NAME}" \
    python2 manage.py shell --command \
    "import backend; backend.models.TemporaryUploadedFile.objects.all().delete()"

  # Restart all old umpire instances.
  ${DOCKER} run \
    --rm \
    --volume /var/run/docker.sock:/var/run/docker.sock \
    --volume "${HOST_DOME_DIR}/${db_filename}:${docker_db_dir}/${db_filename}" \
    --volume "${host_log_dir}:${docker_log_dir}" \
    --workdir "${DOCKER_DOME_DIR}" \
    "${DOCKER_IMAGE_NAME}" \
    python2 manage.py restart_old_umpire
}

do_run() {
  check_docker

  # stop and remove old containers
  stop_and_remove_container "${DOME_UWSGI_CONTAINER_NAME}"
  stop_and_remove_container "${DOME_NGINX_CONTAINER_NAME}"

  do_prepare_dome

  local docker_db_dir="/var/db/factory/dome"
  local db_filename="db.sqlite3"
  local docker_log_dir="/var/log/dome"
  local host_log_dir="${HOST_DOME_DIR}/log"

  # start uwsgi, the bridge between django and nginx
  # Note 'docker' currently reads from '/var/run/docker.sock', which does not
  # follow FHS 3.0
  ${DOCKER} run \
    --detach \
    --restart unless-stopped \
    --name "${DOME_UWSGI_CONTAINER_NAME}" \
    --volume /var/run/docker.sock:/var/run/docker.sock \
    --env HOST_SHARED_DIR="${HOST_SHARED_DIR}" \
    --env HOST_UMPIRE_DIR="${HOST_UMPIRE_DIR}" \
    --env HOST_TFTP_DIR="${HOST_TFTP_DIR}" \
    --env HOST_LOCALTIME_PATH="${HOST_LOCALTIME_PATH}" \
    --volume /run \
    --volume "${HOST_DOME_DIR}/${db_filename}:${docker_db_dir}/${db_filename}" \
    --volume "${host_log_dir}:${docker_log_dir}" \
    --volume "${HOST_TFTP_DIR}:${DOCKER_TFTP_DIR_IN_DOME}" \
    --volume "${HOST_UMPIRE_DIR}:${DOCKER_UMPIRE_DIR_IN_DOME}" \
    --volume "${HOST_SHARED_TMP_VOLUME}:${DOCKER_SHARED_TMP_DIR}" \
    ${DOCKER_LOCALTIME_VOLUME} \
    --workdir "${DOCKER_DOME_DIR}" \
    "${DOCKER_IMAGE_NAME}" \
    uwsgi --ini uwsgi.ini

  # start nginx
  ${DOCKER} run \
    --detach \
    --restart unless-stopped \
    --name "${DOME_NGINX_CONTAINER_NAME}" \
    --volumes-from "${DOME_UWSGI_CONTAINER_NAME}" \
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
  local builder_workdir="${DOCKER_DOME_FRONTEND_DIR}"
  local builder_dockerfile="${DOME_DIR}/docker/Dockerfile.builder"
  local builder_container_name="dome_builder"
  local builder_image_name="${DOME_BUILDER_IMAGE_NAME}"

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
    "${builder_container_name}:${builder_workdir}/build/${builder_output_file}" \
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
  local builder_dockerfile="${OVERLORD_DIR}/Dockerfile"
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
  local release_mode="$1"
  local is_local=1

  if [ "${release_mode}" = "publish" ]; then
    is_local=0
  fi

  check_docker

  local dome_builder_output_file="frontend.tar"
  local overlord_output_file="overlord.tar.gz"

  do_build_dome_deps "${dome_builder_output_file}"
  do_build_overlord "${overlord_output_file}"

  local dockerfile="${SCRIPT_DIR}/Dockerfile"

  fetch_resource "${BUILD_DIR}/docker.tgz" \
    "${RESOURCE_DOCKER_URL}" "${RESOURCE_DOCKER_SHA1}"
  fetch_resource "${BUILD_DIR}/pixz.tbz2" \
    "${RESOURCE_PIXZ_URL}" "${RESOURCE_PIXZ_SHA1}"

  if check_git_status; then
    NEW_DOCKER_IMAGE_GITHASH="$(get_git_hash)"
  else
    # There are some uncommitted changes.
    NEW_DOCKER_IMAGE_GITHASH="*$(get_git_hash)"
  fi
  NEW_DOCKER_IMAGE_TIMESTAMP="$(date '+%Y%m%d%H%M%S')"

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
    --build-arg docker_image_githash="${NEW_DOCKER_IMAGE_GITHASH}" \
    --build-arg docker_image_islocal="${is_local}" \
    --build-arg docker_image_timestamp="${NEW_DOCKER_IMAGE_TIMESTAMP}" \
    "${FACTORY_DIR}"

  echo "${DOCKER_IMAGE_NAME} image successfully built."
}

do_get_changes() {
  local changes_file="$1"

  # Check local modification.
  if ! check_git_status; then
    die "Your have uncommitted or untracked changes.  " \
        "To publish you have to build without local modification."
  fi

  local githash="$(get_git_hash)"
  # Check if the head is already on remotes/cros/master.
  local upstream="$(run_in_factory \
    git merge-base remotes/m/master "${githash}")"
  if [ "${githash}" != "${upstream}" ]; then
    die "Your latest commit was not merged to upstream (remotes/m/master)." \
        "To publish you have to build without local commits."
  fi

  local source_list=(
      setup/Dockerfile
      setup/cros_docker.sh
      sh/cros_payload.sh
      py/dome
      py/instalog
      py/umpire
      ':(exclude)py/umpire/client'
      go/src/overlord
  )

  run_in_factory \
    git log --oneline ${DOCKER_IMAGE_GITHASH}.. "${source_list[@]}" |
    grep -v " ${COMMIT_SUBJECT} " >"${changes_file}"

  if [ -s "${changes_file}" ]; then
    echo "Server related changes since last build (${DOCKER_IMAGE_BUILD}):"
    cat "${changes_file}"
    echo "---"
  else
    # TODO(hungte) Make an option to allow forced publishing.
    die "No server related changes since last publish."
  fi
}

do_update_docker_image_version() {
  local script_file="$1"
  local changes_file="$2"

  local branch_name="$(run_in_factory git rev-parse --abbrev-ref HEAD)"
  if [ "${branch_name}" = "HEAD" ]; then
    # We are on a detached HEAD - should start a new branch to work on so
    # do_commit_docker_image_version can create a new commit.
    # This is required before making any changes to ${script_file}.
    run_in_factory repo start "cros_docker_${NEW_DOCKER_IMAGE_TIMESTAMP}" .
  fi

  echo "Update publish information in $0..."
  sed -i "s/${DOCKER_IMAGE_GITHASH}/${NEW_DOCKER_IMAGE_GITHASH}/;
          s/${DOCKER_IMAGE_TIMESTAMP}/${NEW_DOCKER_IMAGE_TIMESTAMP}/" \
    "${script_file}"
}

do_reload_docker_image_info() {
  local script_file="$1"
  DOCKER_IMAGE_GITHASH="$(sed -n 's/^DOCKER_IMAGE_GITHASH="\(.*\)"/\1/p' \
                          "${script_file}")"
  DOCKER_IMAGE_TIMESTAMP="$(sed -n 's/^DOCKER_IMAGE_TIMESTAMP="\(.*\)"/\1/p' \
                            "${script_file}")"
  set_docker_image_info
}

do_commit_docker_image_release() {
  local changes_file="$1"

  run_in_factory git commit -a -s -m \
    "${COMMIT_SUBJECT} ${DOCKER_IMAGE_TIMESTAMP}.

A new release of cros_docker image on ${DOCKER_IMAGE_TIMESTAMP},
built from source using hash ${DOCKER_IMAGE_GITHASH}.
Published as ${DOCKER_IMAGE_FILENAME}.

Major changes:
$(cat "${changes_file}")

BUG=chromium:679609
TEST=None"
  run_in_factory git show HEAD
  echo "Uploading to gerrit..."
  run_in_factory repo upload --cbr --no-verify .
}

do_publish() {
  check_gsutil

  local changes_file="$(mktemp)"
  TEMP_OBJECTS=("${changes_file}" "${TEMP_OBJECTS[@]}")
  do_get_changes "${changes_file}"

  do_build publish  # make sure we have the newest image

  local script_file="$(realpath "$0")"
  do_update_docker_image_version "${script_file}" "${changes_file}" ||
    die "Failed updating docker image version."

  do_reload_docker_image_info "${script_file}"

  local factory_server_image_url="${GSUTIL_BUCKET}/${DOCKER_IMAGE_FILENAME}"
  if gsutil stat "${factory_server_image_url}" >/dev/null 2>&1; then
    die "${DOCKER_IMAGE_FILENAME} is already on chromeos-localmirror"
  fi

  local temp_dir="$(mktemp -d)"
  TEMP_OBJECTS=("${temp_dir}" "${TEMP_OBJECTS[@]}")

  (cd "${temp_dir}"; do_save)
  upload_to_localmirror "${temp_dir}/${DOCKER_IMAGE_FILENAME}" \
    "${factory_server_image_url}"

  do_commit_docker_image_release "${changes_file}"
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

  curl -L --fail "${RESOURCE_CROS_DOCKER_URL}" | base64 --decode >"${temp_file}"
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

do_passwd() {
  local username="${1:-admin}"

  check_docker
  check_container_status "${DOME_UWSGI_CONTAINER_NAME}"

  ${DOCKER} exec -it "${DOME_UWSGI_CONTAINER_NAME}" \
    python2 manage.py changepassword "${username}"
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

  $0 passwd [username]
      Change the password of a given username. Default username is 'admin'.

common use case:
  - Run "$0 pull" to download docker images, and copy files listed on screen
    to the target computer.
  - Run "$0 install" on the target computer to load docker images.
  - Run "$0 run" to start Dome.
  - Run "$0 passwd" to change password (default: admin/test0000).

commands for developers:
  $0 build
      Build factory server docker image.

  $0 publish
      Build and publish factory server docker image to chromeos-localmirror.

  $0 save
      Save factory server docker image to the current working directory.

  $0 goofy [subcommand]
      Commands to run Goofy in Docker, see "$0 goofy help" for detail.

  $0 umpire [subcommand]
      Commands for Umpire, see "$0 umpire help" for detail.

  $0 overlord [subcommand]
      Commands for Overlord, see "$0 overlord help" for detail.

  $0 dev
      Commands for development server for Dome, see "$0 dev help" for detail.

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
    passwd)
      shift
      do_passwd "$@"
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
    goofy)
      shift
      goofy_main "$@"
      ;;
    umpire)
      shift
      umpire_main "$@"
      ;;
    overlord)
      shift
      overlord_main "$@"
      ;;
    dev)
      shift
      dev_main "$@"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
