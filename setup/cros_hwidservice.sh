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
  gcloud auth application-default --project "${GCP_PROJECT}" login
}

get_ip_from_gcloud() {
  local temp_ip_file="$(mktemp)"
  TEMP_OBJECTS=("${temp_ip_file}" "${TEMP_OBJECTS[@]}")

  gsutil cp "${HWID_SERVICE_IP_FILE_URL}" "${temp_ip_file}"

  # The file pattern is:
  # prod: 1.2.3.4
  # staging: 2.3.4.5
  # dev: 3.4.5.6
  grep "${GCP_PROJECT_ABBREV}:" "${temp_ip_file}" | awk '{ print $2 }'
}

# Host base directories
HOST_SCRIPT_DIR="$(dirname "$(realpath "$0")")"
HOST_FACTORY_DIR="$(dirname "${HOST_SCRIPT_DIR}")"
HOST_CROS_PLATFORM_DIR="$(dirname "${HOST_FACTORY_DIR}")"
HOST_CROS_SRC_DIR="$(dirname "${HOST_CROS_PLATFORM_DIR}")"
HOST_HWIDSERVICE_DIR="${HOST_FACTORY_DIR}/py/hwid/service"
HOST_HWIDSERVICE_CONFIG_DIR="${HOST_HWIDSERVICE_DIR}/config"
HOST_HWIDSERVICE_DOCKER_DIR="${HOST_HWIDSERVICE_DIR}/docker_env"
HOST_HWIDSERVICE_APPENGINE_DIR="${HOST_HWIDSERVICE_DIR}/appengine2"

# Available project names: google.com:croshwid, google.com:croshwid-dev,
# google.com:croshwid-staging
GCP_PROJECT_PROD="google.com:croshwid"
GCP_PROJECT=""
GCP_PROJECT_ABBREV=""
GCP_PROJECT_SUFFIX=""
HWID_SERVICE_IP_FILE_URL="gs://hwid-service/ip.txt"

# GKE and Docker variables
GKE_ZONE="us-central1-a"
GKE_HWID_SERVICE=""
GKE_HWID_SERVICE_CLUSTER=""
GKE_HWID_SERVICE_DEPLOY=""
GKE_CONFIG="${HOST_HWIDSERVICE_CONFIG_DIR}/gke.yaml"
HWID_SERVICE_IMAGE=""
TIME_TAG="$(date +%b-%d-%Y_%H%M)"
LATEST_TAG="latest"
DEFAULT_KUBECTL_PROXY_PORT="8081"

do_build() {
  check_docker

  local dockerfile="${HOST_HWIDSERVICE_DIR}/Dockerfile"

  # A hack to make the build context small.
  local ignore_list=""
  ignore_list+="*\n"
  ignore_list+="!platform/factory\n"
  ignore_list+="!platform/chromeos-hwid\n"
  ignore_list+="!platform2/regions\n"
  ignore_list+="platform/factory/build/*\n"
  local docker_ignore="${HOST_CROS_SRC_DIR}"/.dockerignore
  TEMP_OBJECTS=("${docker_ignore}" "${TEMP_OBJECTS[@]}")
  echo -e "${ignore_list}" > "${docker_ignore}"

  ${DOCKER} build \
    --file "${dockerfile}" \
    --tag "${HWID_SERVICE_IMAGE}:${TIME_TAG}" \
    --tag "${HWID_SERVICE_IMAGE}:${LATEST_TAG}" \
    "${HOST_CROS_SRC_DIR}"
}

do_publish() {
  do_build

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
  if ! gcloud container clusters --project "${GCP_PROJECT}" --zone \
      "${GKE_ZONE}" describe "${GKE_HWID_SERVICE_CLUSTER}" &> /dev/null ; then
    gcloud container clusters \
        --project "${GCP_PROJECT}" \
        --zone "${GKE_ZONE}" \
        create "${GKE_HWID_SERVICE_CLUSTER}"
  fi

  local ip=$(get_ip_from_gcloud)

  set_kubectl_context

  # Create the deployment and the service.
  # Replace the <...> with correct information and pipes to kubectl
  sed "s/<SUFFIX>/${GCP_PROJECT_SUFFIX}/; "`
      `"s/<VERSION-TAG>/${TIME_TAG}/; "`
      `"s/<IP>/${ip}/" \
      "${GKE_CONFIG}" | kubectl create -f -

  # Show the current status of the service
  kubectl get services "${GKE_HWID_SERVICE}"

  echo "It may take a while to lauch HWID Service; waitting for EXTERNAL-IP..."
  echo "run 'kubectl get services ${GKE_HWID_SERVICE} --watch'"
}

do_status() {
  check_gcloud
  check_credentials
  set_kubectl_context
  kubectl get -o wide all
}

do_stop() {
  check_gcloud
  check_credentials
  set_kubectl_context
  kubectl delete service "${GKE_HWID_SERVICE}" || true
  kubectl delete deployment "${GKE_HWID_SERVICE_DEPLOY}" || true
}

do_cleanup() {
  do_stop
  gcloud container clusters delete "${GKE_HWID_SERVICE_CLUSTER}" \
    --zone ${GKE_ZONE}
}

do_update() {
  # Publish the latest image to Google Container Registry.
  do_publish

  set_kubectl_context
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
    --project "${GCP_PROJECT}" \
    --zone "${GKE_ZONE}"

  set_kubectl_context
  echo "Open browser to visit http://localhost:${kubectl_proxy_port}/ui"
  echo "Press Ctrl+C to stop proxying"
  kubectl proxy --port "${kubectl_proxy_port}"
}

do_test() {
  check_docker

  do_build

  echo "Running docker image for local test..."
  ${DOCKER} run --net host "${HWID_SERVICE_IMAGE}:${LATEST_TAG}"
}

set_project() {
  case "$1" in
    prod)
      GCP_PROJECT_SUFFIX=""
      ;;
    staging|dev)
      GCP_PROJECT_SUFFIX="-$1"
      ;;
    *)
      print_usage && exit 1
  esac
  GCP_PROJECT_ABBREV="$1"
  GCP_PROJECT="${GCP_PROJECT_PROD}${GCP_PROJECT_SUFFIX}"
  HWID_SERVICE_IMAGE="gcr.io/${GCP_PROJECT/:/\/}/factory_hwid_service"
  GKE_HWID_SERVICE="hwid-service"${GCP_PROJECT_SUFFIX}
  GKE_HWID_SERVICE_CLUSTER="hwid-cluster${GCP_PROJECT_SUFFIX}"
  GKE_HWID_SERVICE_DEPLOY="hwid-node"${GCP_PROJECT_SUFFIX}
}

set_kubectl_context() {
  # To use a speicific kubectl context, we must designate the context first.
  # The command will fail if the cluster haven't created yet.
  gcloud container clusters get-credentials \
    "${GKE_HWID_SERVICE_CLUSTER}" \
    --zone "${GKE_ZONE}" \
    --project "${GCP_PROJECT}"
}

print_usage() {
  cat << __EOF__
HWID Service: HWID Validating Service

usage: $0 [-p=prod | staging | dev] commands

commands:
  $0 help
      Shows this help message.

  $0 appengine [subcommand]
      Commands for HWIDServiceProxy, see "$0 appengine help" for detail.

  $0 build
      Sets up HWID Service Docker image.

  $0 publish
      Runs build and publish to Google Container Registry.

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

do_appengine_deploy() {
  check_gcloud
  check_credentials

  local config_file="${HOST_HWIDSERVICE_APPENGINE_DIR}/config.py"
  local ip="$(get_ip_from_gcloud)"
  local port="8181"

  # Generate env.py, the file will be imported by hwid_service_proxy.py
  echo "GKE_HWID_SERVICE_URL='http://${ip}:${port}/'" > "${config_file}"
  TEMP_OBJECTS=("${config_file}" "${TEMP_OBJECTS[@]}")

  gcloud --project="${GCP_PROJECT}" \
    app deploy "${HOST_HWIDSERVICE_APPENGINE_DIR}/app.yaml"
}

print_appengine_usage() {
  cat << __EOF__
HWID Service Proxy: Delagating RPCs from AppEngine to HWIDService.

usage: $0 [-p=prod | staging | dev] appengine subcommand

commands:
  $0 appengine deploy
      Deploy HWIDServiceProxy on AppEngine.

__EOF__
}

appengine_main() {
  case "$1" in
    deploy)
      do_appengine_deploy
      ;;
    *)
      print_appengine_usage && exit 1
      ;;
  esac
}

main() {
  while getopts "p:" flag; do
    case ${flag} in
      p)
        set_project "${OPTARG}"
        ;;
      *)
        print_usage && exit 1
        ;;
    esac
  done
  shift "$((OPTIND - 1))"

  case "$1" in
    appengine)
      shift
      appengine_main "$@"
      ;;
    build)
      do_build
      ;;
    test)
      do_test
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
    update)
      do_update
      ;;
    *)
      print_usage && exit 1
      ;;
  esac
}

main "$@"
