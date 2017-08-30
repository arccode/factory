#!/bin/bash
# Copyright 2017 The Chromium OS Authors. All rights reserved.
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

realpath() {
  # Try to find "realpath" in a portable way.
  if type python >/dev/null 2>&1; then
    python -c 'import sys; import os; print os.path.realpath(sys.argv[1])' "$1"
  else
    readlink -f "$@"
  fi
}

die() {
  echo "ERROR: $*"
  exit 1
}

warn() {
  echo "WARNING: $*"
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
  local error_message=""
  error_message+="Require Docker version >= ${DOCKER_VERSION} but you have "
  error_message+="${docker_version}"
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

check_gcloud() {
  if ! type gcloud >/dev/null 2>&1; then
    die "Cannot find gcloud, please install gsutil first"
  fi
  if ! type kubectl >/dev/null 2>&1; then
    die "Cannot find kubectl, install with 'gcloud components install kubectl'"
  fi
}

check_credentials() {
  check_gcloud

  ids="$(gcloud auth list --filter=status:ACTIVE --format="value(account)")"
  for id in ${ids}; do
    if [[ "${id}" =~ .*"@google.com" ]]; then
      return 0
    fi
  done
  gcloud auth application-default --project "${GKE_PROJECT}" login
}

# Host base directories
HOST_SCRIPT_DIR="$(dirname "$(realpath "$0")")"
HOST_FACTORY_DIR="$(dirname "${HOST_SCRIPT_DIR}")"
HOST_CROS_PLATFORM_DIR="$(dirname "${HOST_FACTORY_DIR}")"
HOST_CROS_SRC_DIR="$(dirname "${HOST_CROS_PLATFORM_DIR}")"
HOST_HWIDSERVICE_DIR="${HOST_FACTORY_DIR}/py/hwid/service"
HOST_HWIDSERVICE_CONFIG_DIR="${HOST_HWIDSERVICE_DIR}/config"
HOST_HWIDSERVICE_DOCKER_DIR="${HOST_HWIDSERVICE_DIR}/docker_env"

# GKE and Docker variables
GKE_ZONE="asia-east1-c"
GKE_PROJECT="chromeos-factory"
GKE_HWID_SERVICE_CLUSTER="factory-hwid-service-cluster"
GKE_HWID_SERVICE="factory-hwid-service-node"
GKE_HWID_SERVICE_DEPLOY="factory-hwid-service-deploy-node"
GKE_SERVICE_CONFIG="${HOST_HWIDSERVICE_CONFIG_DIR}/service.yaml"
GKE_DEPLOYMENT_CONFIG="${HOST_HWIDSERVICE_CONFIG_DIR}/deployment.yaml"
HWID_SERVICE_IMAGE="gcr.io/chromeos-factory/factory_hwid_service"
TIME_TAG="$(date +%b-%d-%Y_%H%M)"
LATEST_TAG="latest"
DEFAULT_KUBECTL_PROXY_PORT="8081"

do_setup() {
  check_docker

  # Used for pulling internal repos.
  local gitcookies_path="$(git config --get "http.cookiefile")"
  local temp_gitcookies_path="${HOST_HWIDSERVICE_DOCKER_DIR}/.gitcookies"
  local dockerfile="${HOST_HWIDSERVICE_DOCKER_DIR}/Dockerfile.hwidservice"

if [ ! -f "${gitcookies_path}" ]; then
    echo "HWID Service setup failed. No such file ${gitcookies_path}" && false
  fi

  # Prepare out of Docker context file.
  cp "${gitcookies_path}" "${temp_gitcookies_path}"
  chmod 600 "${temp_gitcookies_path}"
  TEMP_OBJECTS=("${temp_gitcookies_path}" "${TEMP_OBJECTS[@]}")

  ${DOCKER} build \
    --file "${dockerfile}" \
    --tag "${HWID_SERVICE_IMAGE}:${TIME_TAG}" \
    --tag "${HWID_SERVICE_IMAGE}:${LATEST_TAG}" \
    "${HOST_HWIDSERVICE_DOCKER_DIR}"
}

do_publish() {
  do_setup

  check_gcloud
  check_credentials
  gcloud docker -- push "${HWID_SERVICE_IMAGE}:${TIME_TAG}"
  # Won't do push, just tag the image on Google Container Registry.
  gcloud docker -- push "${HWID_SERVICE_IMAGE}:${LATEST_TAG}"
  echo "Published HWID Service Image to Google Container Registry" \
       "https://${HWID_SERVICE_IMAGE}"
}

do_run() {

  do_publish
  check_gcloud
  check_credentials

  # Create cluster if there is no one.
  if ! gcloud container clusters --project "${GKE_PROJECT}" --zone \
      "${GKE_ZONE}" describe "${GKE_HWID_SERVICE_CLUSTER}" &> /dev/null ; then
    gcloud container clusters \
        --project "${GKE_PROJECT}" \
        --zone "${GKE_ZONE}" \
        create "${GKE_HWID_SERVICE_CLUSTER}"
  fi

  # Run container if there is no one.
  if ! kubectl get deployment "${GKE_HWID_SERVICE_DEPLOY}" &> /dev/null ; then
    echo "Deploying container image..."
    # Replace the <VERSION-TAG> with time tag string and pipes to kubectl
    sed "s/<VERSION-TAG>/${TIME_TAG}/" "${GKE_DEPLOYMENT_CONFIG}" \
        | kubectl create -f -
  fi

  # Create the service.
  kubectl create -f "${GKE_SERVICE_CONFIG}"

  # Show the current status of the service
  kubectl get services "${GKE_HWID_SERVICE}"

  echo "It may take a while to lauch HWID Service; waitting for EXTERNAL-IP..."
  echo "run 'kubectl get services ${GKE_HWID_SERVICE} --watch'"
}

do_status() {
  check_gcloud
  check_credentials
  kubectl get -o wide all
}

do_stop() {
  check_gcloud
  check_credentials
  kubectl delete service "${GKE_HWID_SERVICE}" || true
  kubectl delete deployment "${GKE_HWID_SERVICE_DEPLOY}" || true
}

do_cleanup() {
  check_gcloud
  check_credentials
  kubectl delete service "${GKE_HWID_SERVICE}" || true
  kubectl delete deployment "${GKE_HWID_SERVICE_DEPLOY}" || true
  gcloud container clusters delete "${GKE_HWID_SERVICE_CLUSTER}" \
    --zone ${GKE_ZONE}
}

do_update() {
  # Publish the latest image to Google Container Registry.
  do_publish

  kubectl set image "deployment/${GKE_HWID_SERVICE_DEPLOY}" \
    "${GKE_HWID_SERVICE_DEPLOY}=${HWID_SERVICE_IMAGE}:${TIME_TAG}"
}

do_connect() {
  local kubectl_proxy_port="${DEFAULT_KUBECTL_PROXY_PORT}"

  if [ ! -z "$1" ]; then
    kubectl_proxy_port="$1"
  fi

  check_gcloud

  gcloud container clusters \
    get-credentials "${GKE_HWID_SERVICE_CLUSTER}" \
    --project "${GKE_PROJECT}" \
    --zone "${GKE_ZONE}"

  echo "Open browser to visit http://localhost:${kubectl_proxy_port}/ui"
  echo "Press Ctrl+C to stop proxying"
  kubectl proxy --port "${kubectl_proxy_port}"
}

do_test() {
  check_docker

  local dockerfile="${HOST_HWIDSERVICE_DIR}/Dockerfile.test"
  local hwidservice_test_image_tag="factory_hwid_service_local_test"

  # A hack to make the build context small.
  local ignore_list=""
  ignore_list+="*\n"
  ignore_list+="!platform/factory\n"
  ignore_list+="!platform/chromeos-hwid\n"
  ignore_list+="!platform2/regions\n"
  local docker_ignore="${HOST_CROS_SRC_DIR}"/.dockerignore
  TEMP_OBJECTS=("${docker_ignore}" "${TEMP_OBJECTS[@]}")
  echo -e "${ignore_list}" > "${docker_ignore}"

  echo "Building docker image..."
  ${DOCKER} build \
    --file "${dockerfile}" \
    --tag "${hwidservice_test_image_tag}" \
    "${HOST_CROS_SRC_DIR}"

  echo "Running docker image..."
  ${DOCKER} run \
    --net host \
    "${hwidservice_test_image_tag}"
}

print_usage() {
  cat << __EOF__
HWID Service: HWID Validating Service

commands:
  $0 help
      Shows this help message.

  $0 setup
      Sets up HWID Service Docker image.

  $0 publish
      Runs setup and publish to Google Container Registry.

  $0 run
      Runs HWID Service Docker image.

  $0 status
      Shows the HWID Service status on Google Container Engine.

  $0 stop
      Stops HWID Service running on Google Container Engine.

  $0 cleanup
      Stops and cleans up Google Container Engine resources.

  $0 connect [port]
      Connects to Kubectl control panel.

  $0 update
      Updates the HWID Service image on Google Container Engine.

  $0 test
      Test Factory HWID Service in localhost.
__EOF__
}

main() {
  case "$1" in
    setup)
      do_setup
      ;;
    publish)
      do_publish
      ;;
    run)
      do_run
      ;;
    status)
      do_status
      ;;
    stop)
      do_stop
      ;;
    cleanup)
      do_cleanup
      ;;
    connect)
      shift
      do_connect "$@"
      ;;
    test)
      do_test
      ;;
    update)
      do_update
      ;;
    *)
      print_usage && exit 1
      ;;
  esac
}

main "$@"
