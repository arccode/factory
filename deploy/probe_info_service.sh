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

LOCAL_DEPLOYMENT_SERVICE_SIDS=()

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
  load_config "staging"  # Leverage the staging config for GCP_PROJECT ID.

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

  info "Start the dependent services."
  local sid="$(setsid bash -c "gcloud --project='${GCP_PROJECT}' beta \
      emulators datastore start --no-store-on-disk 2>/dev/null >/dev/null \
      & echo \$\$")"
  sleep 3  # ensure the datastore emulator is ready
  LOCAL_DEPLOYMENT_SERVICE_SIDS+=("${sid}")
  $(gcloud --project="${GCP_PROJECT}" beta emulators datastore env-init)
}

local_deployment_stop() {
  info "Stop all dependent services."
  local pid
  for pid in "${LOCAL_DEPLOYMENT_SERVICE_SIDS[@]}"; do
    pkill -s "${pid}"
  done
}

local_deployment_run_venv_python() {
  run_in_dir "${LOCAL_DEPLOYMENT_PROJECT_ROOT_PATH}" \
      exec "${LOCAL_DEPLOYMENT_VENV_PYTHON_PATH}" "$@"
}

local_deployment_find_all_test_modules() {
  local find_output="$(find "${LOCAL_DEPLOYMENT_PROJECT_ROOT_PATH}" -type f \
      -name "*_*test.py" -printf "%P\\n")"
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

  local_deployment_stop
}

do_run_tests() {
  set +e  # Temporary turns off non-zero status check for the shflags library.
  local_deployment_define_flags
  DEFINE_boolean dump_logs "${FLAGS_FALSE}" "Dump logs of the failure tests."
  FLAGS_HELP="USAGE: $0 [flags] [<test_modules>...]"
  FLAGS "$@" || die $?
  set -e

  local_deployment_prepare

  eval local "test_modules=(${FLAGS_ARGV})"
  if [ "${#test_modules[@]}" -eq 0 ]; then
    info "Discover all test modules."
    test_modules=($(local_deployment_find_all_test_modules))
    info "Found ${#test_modules[@]} test modules."
  fi

  local failed_test_modules=()
  local log_dir="$(local_deployment_create_log_dir "test")"

  local test_module=
  for test_module in "${test_modules[@]}"; do
    info "Run test \"${test_module}\"."
    local logfile_path="${log_dir}/${test_module}.log"
    if ! local_deployment_run_venv_python -m "${test_module}" \
        >"${logfile_path}" 2>&1; then
      failed_test_modules+=("${test_module}")
    fi
  done

  local_deployment_stop

  if [ ${#failed_test_modules[@]} -eq 0 ]; then
    info "All tests are passed!"
    return
  fi

  error "Following ${#failed_test_modules[@]} test(s) are failed:"
  for test_module in "${failed_test_modules[@]}"; do
    local logfile_path="${log_dir}/${test_module}.log"
    echo "-  ${test_module}, logfile path: ${logfile_path}"
    if [ "${FLAGS_dump_logs}" == "${FLAGS_TRUE}" ]; then
      echo "========== BEGIN: LOG =========="
      cat "${logfile_path}"
      echo "========== END: LOG =========="
    fi
  done
  die "Fail rate ${#failed_test_modules[@]}/${#test_modules[@]} > 0."
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

  $0 test [<args...>]
      Runs the specified/all tests.  The command prepares the virtualenv and
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
    test)
      do_run_tests "$@"
      ;;
    *)
      die "Unknown sub-command: \"${subcmd}\".  Run \`${0} help\` to print" \
          "the usage."
      ;;
  esac

  mk_success
}

main "$@"
