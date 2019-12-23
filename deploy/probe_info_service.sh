#!/bin/bash
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
FACTORY_DIR="$(readlink -f "${SCRIPT_DIR}/..")"
FACTORY_PRIVATE_DIR="${FACTORY_DIR}/../factory-private"

. "${FACTORY_DIR}/devtools/mk/common.sh" || exit 1
. "${FACTORY_PRIVATE_DIR}/config/probe_info_service/config.sh" || exit 1

PROBE_INFO_SERVICE_DIR="${FACTORY_DIR}/py/probe_info_service"

# Following variables will be assigned by `load_config <DEPLOYMENT_TYPE>`
GCP_PROJECT=

run_in_dir() {
  local working_dir="$1"
  shift
  (cd "${working_dir}"; "$@")
}

do_deploy() {
  local deployment_type="$1"

  if ! load_config "${deployment_type}"; then
    die "Unsupported deployment type: \"${deployment_type}\"."
  fi

  local tmpdir="$(mktemp -d)"
  if [ ! -d "${tmpdir}" ]; then
    die "Failed to create a temporary placeholder for files to deploy."
  fi
  add_temp "${tmpdir}"

  make -C "${PROBE_INFO_SERVICE_DIR}" PACK_DEST_DIR="${tmpdir}" _pack

  run_in_dir "${tmpdir}" gcloud --project="${GCP_PROJECT}" app deploy app.yaml
}

print_usage() {
  cat << __EOF__
Chrome OS Probe Info Service Deployment Script

commands:
  $0 help
      Shows this help message.

  $0 deploy staging
      Deploys Probe Info Service to the given environment by gcloud command.

__EOF__
}

main() {
  local subcmd="$1"
  case "${subcmd}" in
    help)
      print_usage
      ;;
    deploy)
      do_deploy "$2"
      ;;
    *)
      die "Unknown sub-command: \"${subcmd}\".  Run \`${0} help\` to print" \
          "the usage."
      ;;
  esac

  mk_success
}

main "$@"
