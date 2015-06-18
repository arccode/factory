#!/bin/bash
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#

UMPIRE_CONTAINER_NAME="umpire"
UMPIRE_IMAGE_NAME="cros/umpire"

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
BUILDDIR=${SCRIPT_DIR}/umpire_docker
KEYSDIR=${SCRIPT_DIR}/sshkeys
KEYFILE=${KEYSDIR}/testing_rsa
KEYFILE_PUB=${KEYSDIR}/testing_rsa.pub
HOST_DIR=/shared
SSH_OPTIONS='-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no'

die() {
  echo "ERROR: $@"
  exit 1
}

check_docker() {
  if ! type docker >/dev/null 2>&1; then
    die "Docker not installed, abort."
  fi
}

check_status() {
  local container_name="$1"
  local status="$(sudo docker ps | grep ${container_name} | grep Up)"

  if [ -z "${status}" ]; then
    die "${UMPIRE_CONTAINER_NAME} container is not running"
  fi
}

get_container_IP() {
  local container_name="$1"
  check_status "${container_name}"

  sudo docker inspect "${container_name}" | \
    awk '/IPAddress/ { gsub(/[",]/, "", $2); print $2 }'
}

do_ssh() {
  check_docker

  local container_name="$1"
  check_status "${container_name}"
  shift

  local ip="$(get_container_IP ${container_name})"
  ssh ${SSH_OPTIONS} -i ${KEYFILE} root@${ip} $@
}

do_build() {
  check_docker

  # docker build requires resource to be in the build directory, copy keyfile
  # for using as authorized_keys
  cp -f ${KEYFILE_PUB} ${BUILDDIR}/authorized_keys

  sudo docker build -t ${UMPIRE_IMAGE_NAME} ${BUILDDIR}
  if [ $? -eq 0 ]; then
    echo "${UMPIRE_CONTAINER_NAME} container successfully built."
  fi

  # Cleanup
  rm ${BUILDDIR}/authorized_keys
}

do_destroy() {
  check_docker

  echo -n "Deleting ${UMPIRE_CONTAINER_NAME} container ... "
  sudo docker stop "${UMPIRE_CONTAINER_NAME}" >/dev/null 2>&1
  sudo docker rm "${UMPIRE_CONTAINER_NAME}" >/dev/null 2>&1
  echo "done"
}

do_start() {
  check_docker

  echo -n "Starting ${UMPIRE_CONTAINER_NAME} container ... "
  sudo mkdir -p ${HOST_DIR}
  sudo docker start "${UMPIRE_CONTAINER_NAME}" >/dev/null 2>&1

  # Container does not exist, run a new one
  if [ $? -ne 0 ]; then
    local umpire_port_map=""
    for base in $(seq 8080 10 8380); do
      p1=${base}              # Imaging
      p2=$(expr ${base} + 2)  # Shopfloor
      p3=$(expr ${base} + 6)  # Rsync
      umpire_port_map="-p $p1:$p1 -p $p2:$p2 -p $p3:$p3 ${umpire_port_map}"
    done

    sudo docker run -d \
      --privileged \
      -p 4455:4455 \
      -p 9000:9000 \
      ${umpire_port_map} \
      -v ${HOST_DIR}:/mnt \
      --name "${UMPIRE_CONTAINER_NAME}" \
      "${UMPIRE_IMAGE_NAME}" >/dev/null 2>&1
  fi
  echo "done"

  echo -e '\n*** NOTE ***'
  echo "- Host directory ${HOST_DIR} is mounted under /mnt in the container."
  echo '- Umpire service ports is mapped to the local machine.'
  echo '- Overlord service ports 4455, 9000 is mapped to the local machine.'
}

do_stop() {
  check_docker

  echo -n "Stopping ${UMPIRE_CONTAINER_NAME} container ... "
  sudo docker stop "${UMPIRE_CONTAINER_NAME}" >/dev/null 2>&1
  echo "done"
}

do_install() {
  local container_name="$1"
  local board="$2"
  local toolkit="$3"
  check_status "${container_name}"

  if [ ! -e "${toolkit}" ]; then
    die "Factory toolkit '${toolkit}' does not exist, abort."
  fi

  check_docker

  local ip=$(get_container_IP "${UMPIRE_CONTAINER_NAME}")
  scp ${SSH_OPTIONS} -i ${KEYFILE} ${toolkit} root@${ip}:/tmp
  ssh ${SSH_OPTIONS} -i ${KEYFILE} root@${ip} \
    /tmp/${toolkit##*/} -- --init-umpire-board=${board}
  ssh ${SSH_OPTIONS} -i ${KEYFILE} root@${ip} \
    "echo export BOARD=${board} >> /root/.bashrc"
  ssh ${SSH_OPTIONS} -i ${KEYFILE} root@${ip} restart umpire BOARD=${board}
}

usage() {
  cat << __EOF__
Usage: $0 COMMAND [arg ...]

Commands:
    build       build umipre container
    destroy     destroy umpire container
    start       start umpire container
    stop        stop umpire container
    ssh         ssh into umpire container
    ip          get umpire container IP
    install     install factory toolkit
    help        Show this help message

Sub-Command options:
    install     BOARD FACTORY_TOOLKIT_FILE
    ssh         SSH_ARGS

Options:
    -h, --help  Show this help message
__EOF__
}

main() {
  case "$1" in
    build)
      do_build
      ;;
    destroy)
      do_destroy
      ;;
    start)
      do_start
      ;;
    stop)
      do_stop
      ;;
    ssh)
      shift
      do_ssh "${UMPIRE_CONTAINER_NAME}" "$@"
      ;;
    ip)
      get_container_IP "${UMPIRE_CONTAINER_NAME}"
      ;;
    install)
      shift
      do_install "${UMPIRE_CONTAINER_NAME}" "$@"
      ;;
    *|help|-h|--help)
      usage
      ;;
  esac
}

main "$@"
