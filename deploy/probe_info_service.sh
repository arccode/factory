#!/bin/bash
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
FACTORY_DIR="$(readlink -f "${SCRIPT_DIR}/..")"
FACTORY_PRIVATE_DIR="${FACTORY_DIR}/../factory-private"

. "${FACTORY_DIR}/devtools/mk/common.sh" || exit 1
. "${FACTORY_DIR}/devtools/aufs/shflags" || exit 1
. "${FACTORY_PRIVATE_DIR}/config/probe_info_service/config.sh" || exit 1

PROBE_INFO_SERVICE_DIR="${FACTORY_DIR}/py/probe_info_service"

VENV_PYTHON_NAME="python3"
VENV_PYTHON_RELPATH="./bin/${VENV_PYTHON_NAME}"

: "${LOCAL_DEPLOYMENT_DIR:=/tmp/probe_info_service}"

LOCAL_DEPLOYMENT_VENV_PATH="${LOCAL_DEPLOYMENT_DIR}/venv"
LOCAL_DEPLOYMENT_VENV_PYTHON_PATH="\
${LOCAL_DEPLOYMENT_VENV_PATH}/bin/${VENV_PYTHON_NAME}"
LOCAL_DEPLOYMENT_PROJECT_ROOT_PATH="${LOCAL_DEPLOYMENT_DIR}/project_root"

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

  info "Create a temporary directory to hold files to deploy."
  local tmpdir="$(mktemp -d)"
  if [ ! -d "${tmpdir}" ]; then
    die "Failed to create a temporary placeholder for files to deploy."
  fi
  add_temp "${tmpdir}"

  info "Prepare the files to deploy."
  make -C "${PROBE_INFO_SERVICE_DIR}" PACK_DEST_DIR="${tmpdir}" _pack

  info "Deploy the app engine."
  run_in_dir "${tmpdir}" gcloud --project="${GCP_PROJECT}" app deploy app.yaml
}

local_deployment_define_flags() {
  DEFINE_boolean clean "${FLAGS_FALSE}" \
      "Clean-up 'PROBE_INFO_SERVICE_VNEV_PATH' gracefully first."
}

local_deployment_prepare() {
  if [ "${FLAGS_clean}" == "${FLAGS_TRUE}" ]; then
    if [[ -f "${LOCAL_DEPLOYMENT_VENV_PYTHON_PATH}" ]]; then
      info "Drop the existing venv."
      rm -rf "${LOCAL_DEPLOYMENT_VENV_PATH}"
    fi
    if [[ -d "${LOCAL_DEPLOYMENT_PROJECT_ROOT_PATH}" ]]; then
      info "Drop the existing project root dir."
      rm -rf "${LOCAL_DEPLOYMENT_PROJECT_ROOT_PATH}"
    fi
  fi

  if [ ! -f "${LOCAL_DEPLOYMENT_VENV_PYTHON_PATH}" ]; then
    info "Initialize venv for local instance."
    virtualenv --python="${VENV_PYTHON_NAME}" "${LOCAL_DEPLOYMENT_VENV_PATH}"
  fi

  info "Copy resources into venv path."
  make -C "${PROBE_INFO_SERVICE_DIR}" \
      PACK_DEST_DIR="${LOCAL_DEPLOYMENT_PROJECT_ROOT_PATH}" _pack

  info "Install dependent package/modules."
  local_deployment_run_venv_python -m pip install -r \
      "${LOCAL_DEPLOYMENT_PROJECT_ROOT_PATH}/requirements.txt"
}

local_deployment_run_venv_python() {
  run_in_dir "${LOCAL_DEPLOYMENT_PROJECT_ROOT_PATH}" \
      exec "${LOCAL_DEPLOYMENT_VENV_PYTHON_PATH}" "$@"
}

local_deployment_find_all_unittest_modules() {
  local find_output="$(find "${LOCAL_DEPLOYMENT_PROJECT_ROOT_PATH}" -type f \
      -name "*_unittest.py" -printf "%P\\n")"
  local path_name=
  IFS=$'\n'
  for path_name in ${find_output}; do
    local path_name_no_ext="${path_name%.py}"
    echo "${path_name_no_ext//\//.}"
  done
}

local_deployment_create_log_dir() {
  local log_type="$1"
  local timestamp="$(date +%Y%m%d_%H%M%S)"
  local log_dir="${LOCAL_DEPLOYMENT_DIR}/logs.${log_type}.${timestamp}.d"
  local log_linkpath="${LOCAL_DEPLOYMENT_DIR}/logs.${log_type}.latest.d"
  mkdir -p "${log_dir}"
  rm "${log_linkpath}" || true
  ln -s "$(basename "${log_dir}")" "${log_linkpath}"
  echo "${log_dir}"
}

do_run_local() {
  set +e  # Temporary turns off non-zero status check for the shflags library.
  local_deployment_define_flags
  FLAGS "$@" || die $?
  set -e

  local_deployment_prepare

  info "Start the local instance."
  local_deployment_run_venv_python \
      -m cros.factory.probe_info_service.app_engine.main
}

do_run_unittests() {
  set +e  # Temporary turns off non-zero status check for the shflags library.
  local_deployment_define_flags
  DEFINE_boolean dump_logs "${FLAGS_FALSE}" "Dump logs of the failure tests."
  FLAGS_HELP="USAGE: $0 [flags] [<unittest_modules>...]"
  FLAGS "$@" || die $?
  set -e

  local_deployment_prepare

  eval local "unittest_modules=(${FLAGS_ARGV})"
  if [ "${#unittest_modules[@]}" -eq 0 ]; then
    info "Discover all unittest modules."
    unittest_modules=($(local_deployment_find_all_unittest_modules))
    info "Found ${#unittest_modules[@]} unittest modules."
  fi

  local failed_unittest_modules=()
  local log_dir="$(local_deployment_create_log_dir "unittest")"

  local unittest_module=
  for unittest_module in "${unittest_modules[@]}"; do
    info "Run unittest \"${unittest_module}\"."
    local logfile_path="${log_dir}/${unittest_module}.log"
    if ! local_deployment_run_venv_python -m "${unittest_module}" \
        >"${logfile_path}" 2>&1; then
      failed_unittest_modules+=("${unittest_module}")
    fi
  done

  if [ ${#failed_unittest_modules[@]} -eq 0 ]; then
    info "All unittests are passed!"
    return
  fi

  error "Following ${#failed_unittest_modules[@]} unittest(s) are failed:"
  for unittest_module in "${failed_unittest_modules[@]}"; do
    local logfile_path="${log_dir}/${unittest_module}.log"
    echo "-  ${unittest_module}, logfile path: ${logfile_path}"
    if [ "${FLAGS_dump_logs}" == "${FLAGS_TRUE}" ]; then
      echo "========== BEGIN: LOG =========="
      cat "${logfile_path}"
      echo "========== END: LOG =========="
    fi
  done
  die "Fail rate ${#failed_unittest_modules[@]}/${#unittest_modules[@]} > 0."
}

print_usage() {
  cat << __EOF__
Chrome OS Probe Info Service Deployment Script

commands:
  $0 help
      Shows this help message.

  $0 deploy staging
      Deploys Probe Info Service to the given environment by gcloud command.

  $0 run [<args...>]
      Runs Probe Info Service locally.  The command prepares the virtualenv and
      the source code to deploy in 'LOCAL_DEPLOYMENT_DIR' (default to
      /tmp/probe_info_service/) first.  Then it starts the server instance
      locally.

  $0 unittest [<args...>]
      Runs the specified/all unittests.  The command prepares the virtualenv and
      the source code to deploy in 'LOCAL_DEPLOYMENT_DIR' (default to
      /tmp/probe_info_service/) first.  Then it runs the targets locally.

To get the detail usages of the sub-commands, please run

  $0 <sub-command> --help

__EOF__
}

main() {
  local subcmd="$1"
  shift || true
  case "${subcmd}" in
    help)
      print_usage
      ;;
    deploy)
      do_deploy "$1"
      ;;
    run)
      do_run_local "$@"
      ;;
    unittest)
      do_run_unittests "$@"
      ;;
    *)
      die "Unknown sub-command: \"${subcmd}\".  Run \`${0} help\` to print" \
          "the usage."
      ;;
  esac

  mk_success
}

main "$@"
