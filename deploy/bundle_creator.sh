#!/bin/bash
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
FACTORY_DIR="$(readlink -f "${SCRIPT_DIR}/..")"
FACTORY_PRIVATE_DIR="${FACTORY_DIR}/../factory-private"
LOCAL_BUILD_BUNDLE="${FACTORY_DIR}/build/bundle"
TOOLKIT_NAME="install_factory_toolkit.run"
LOCAL_BUILD_TOOLKIT="${LOCAL_BUILD_BUNDLE}/toolkit/${TOOLKIT_NAME}"
SOURCE_DIR="${FACTORY_DIR}/py/bundle_creator/"

. "${FACTORY_DIR}/devtools/mk/common.sh" || exit 1
. "${FACTORY_PRIVATE_DIR}/config/bundle_creator/config.sh" || exit 1

# Following variables will be assigned by `load_config <DEPLOYMENT_TYPE>`
GCLOUD_PROJECT=
DOCKER_IMAGENAME=
CONTAINER_IMAGE=
INSTANCE_TEMPLATE_NAME=
INSTANCE_GROUP_NAME=
BUNDLE_BUCKET=
PUBSUB_TOPIC=
PUBSUB_SUBSCRIPTION=
ALLOWED_LOAS_PEER_USERNAMES=
NOREPLY_EMAIL=
FAILURE_EMAIL=

load_config_by_deployment_type() {
  local deployment_type="$1"
  if ! load_config "${deployment_type}"; then
    die "Unsupported deployment type: \"${deployment_type}\"."
  fi
}

build_docker() {
  load_config_by_deployment_type "$1"
  local temp_dir="$(mktemp -d)"
  if [ ! -d "${temp_dir}" ]; then
    die "Failed to create a temporary placeholder for files to deploy."
  fi
  add_temp "${temp_dir}"

  rsync -avr --exclude="app_engine*" --exclude="proto" "${SOURCE_DIR}"/* \
      "${temp_dir}"
  cp "${FACTORY_PRIVATE_DIR}/config/bundle_creator/service_account.json" \
      "${temp_dir}/docker"
  if [ -f "${LOCAL_BUILD_TOOLKIT}" ]; then
    cp "${LOCAL_BUILD_TOOLKIT}" "${temp_dir}/docker"
    cp -rf "${LOCAL_BUILD_BUNDLE}/setup" "${temp_dir}/docker"
  else
    cp -f "/bin/false" "${temp_dir}/docker/${TOOLKIT_NAME}"
    mkdir -p "${temp_dir}/docker/setup"
  fi
  # Fill in env vars in docker/config.py
  env GCLOUD_PROJECT="${GCLOUD_PROJECT}" \
    BUNDLE_BUCKET="${BUNDLE_BUCKET}" \
    PUBSUB_SUBSCRIPTION="${PUBSUB_SUBSCRIPTION}" \
    envsubst < "${SOURCE_DIR}/docker/config.py" > "${temp_dir}/docker/config.py"

  protoc -I "${SOURCE_DIR}/proto/" --python_out "${temp_dir}/docker" \
    "${SOURCE_DIR}/proto/factorybundle.proto"
  docker build -t "${DOCKER_IMAGENAME}" --file "${temp_dir}/docker/Dockerfile" \
    "${temp_dir}"
}

deploy_docker() {
  load_config_by_deployment_type "$1"

  gcloud --project="${GCLOUD_PROJECT}" docker -- push "${DOCKER_IMAGENAME}"
  gcloud --project="${GCLOUD_PROJECT}" compute project-info \
    add-metadata --metadata bundle-creator-docker="${DOCKER_IMAGENAME}"
}

deploy_appengine() {
  load_config_by_deployment_type "$1"
  local temp_dir="$(mktemp -d)"
  if [ ! -d "${temp_dir}" ]; then
    die "Failed to create a temporary placeholder for files to deploy."
  fi
  add_temp "${temp_dir}"

  local factory_dir="${temp_dir}/cros/factory"
  local package_dir="${factory_dir}/bundle_creator"
  mkdir -p "${package_dir}"

  cp -r "${SOURCE_DIR}/app_engine" "${package_dir}"
  cp -r "${SOURCE_DIR}/connector" "${package_dir}"
  local allowed_array=$(printf ", \'%s\'" "${ALLOWED_LOAS_PEER_USERNAMES[@]}")
  allowed_array="${allowed_array:3:$((${#allowed_array}-4))}"
  # Fill in env vars in rpc/config.py
  env GCLOUD_PROJECT="${GCLOUD_PROJECT}" \
    BUNDLE_BUCKET="${BUNDLE_BUCKET}" \
    PUBSUB_TOPIC="${PUBSUB_TOPIC}" \
    ALLOWED_LOAS_PEER_USERNAMES="${allowed_array}" \
    NOREPLY_EMAIL="${NOREPLY_EMAIL}" \
    FAILURE_EMAIL="${FAILURE_EMAIL}" \
    envsubst < "${SOURCE_DIR}/app_engine/config.py" \
    > "${package_dir}/app_engine/config.py"
  mv "${package_dir}/app_engine/app.yaml" "${temp_dir}"
  mv "${package_dir}/app_engine/requirements.txt" "${temp_dir}"

  protoc --python_out="${package_dir}/app_engine" -I "${SOURCE_DIR}/proto" \
      "${SOURCE_DIR}/proto/factorybundle.proto"

  gcloud --project="${GCLOUD_PROJECT}" app deploy \
    "${temp_dir}/app.yaml" --quiet
}

deploy_appengine_legacy() {
  load_config_by_deployment_type "$1"
  local temp_dir=$(mktemp -d)
  if [ ! -d "${temp_dir}" ]; then
    die "Failed to create a temporary placeholder for files to deploy."
  fi
  add_temp "${temp_dir}"

  cp -r "${SOURCE_DIR}"/app_engine_legacy/* "${temp_dir}"
  # Fill in env vars in rpc/config.py
  env BUNDLE_BUCKET="${BUNDLE_BUCKET}" \
    NOREPLY_EMAIL="${NOREPLY_EMAIL}" \
    FAILURE_EMAIL="${FAILURE_EMAIL}" \
    envsubst < "${SOURCE_DIR}/app_engine_legacy/rpc/config.py" \
    > "${temp_dir}/rpc/config.py"

  protoc -o "${temp_dir}/rpc/factorybundle.proto.def" \
    -I "${SOURCE_DIR}" "${SOURCE_DIR}/proto/factorybundle.proto"

  gcloud --project="${GCLOUD_PROJECT}" app deploy \
    "${temp_dir}/app.yaml" --quiet
  gcloud --project="${GCLOUD_PROJECT}" app deploy \
    "${temp_dir}/queue.yaml" --quiet
}

create_vm() {
  load_config_by_deployment_type "$1"
  {
    gcloud beta compute instance-templates --project="${GCLOUD_PROJECT}" \
      create-with-container "${INSTANCE_TEMPLATE_NAME}" \
      --machine-type=custom-8-16384 \
      --network-tier=PREMIUM --maintenance-policy=MIGRATE \
      --image=cos-stable-63-10032-71-0 --image-project=cos-cloud \
      --boot-disk-size=200GB --boot-disk-type=pd-standard \
      --boot-disk-device-name="${INSTANCE_TEMPLATE_NAME}" \
      --container-image="${CONTAINER_IMAGE}" \
      --container-restart-policy=always --container-privileged \
      --labels=container-vm=cos-stable-63-10032-71-0
  } || {
    # The vm instance is managed by the instance group, we usually delete a vm
    # instance by deleting the instance group. And we won't delete the instance
    # template once it is created. So output the message to ignore the error
    # message from the creating template command.
    echo "The specific instance template was created."
  }

  local zone
  zone="us-central1-a"
  local filter
  filter="zone:${zone} name:${INSTANCE_GROUP_NAME}"
  {
    gcloud compute instance-groups managed list --project "${GCLOUD_PROJECT}" \
      --filter="${filter}" | grep "${INSTANCE_GROUP_NAME}"
  } && {
    gcloud compute instance-groups managed delete "${INSTANCE_GROUP_NAME}" \
      --project "${GCLOUD_PROJECT}" \
      --zone "${zone}" \
      --quiet
  }
  gcloud compute instance-groups managed create "${INSTANCE_GROUP_NAME}" \
    --project "${GCLOUD_PROJECT}" \
    --template "${INSTANCE_TEMPLATE_NAME}" \
    --zone "${zone}" \
    --size 1
}

deploy_vm() {
  build_docker "$1"
  deploy_docker "$1"
  create_vm "$1"
}

print_usage() {
  cat << __EOF__
Easy Bundle Creation Service Deployment Script

commands:
  $0 build-docker [prod|staging|dev|dev2]
      Build the image from the \`Dockerfile\` located at
      \`factory/py/bundle_creator/docker/Dockerfile\`.

  $0 deploy [prod|staging|dev|dev2]
      Do \`deploy-appengine\`, \`deploy-appengine-legacy\` and \`deploy-vm\`
      commands.

  $0 deploy-docker [prod|staging|dev|dev2]
      Push the docker image built from the command \`build-docker\` to the
      Container Registry.

  $0 deploy-appengine [prod|staging|dev|dev2]
      Deploy the code and configuration under
      \`factory/py/bundle_creator/app_engine\` to App Engine.

  $0 deploy-appengine-legacy [prod|staging|dev|dev2]
      Deploy the code and configuration under
      \`factory/py/bundle_creator/app_engine_legacy\` to App Engine.

  $0 create-vm [prod|staging|dev|dev2]
      Create a compute engine instance which use the docker image deployed by
      the command \`deploy-docker\`.

  $0 deploy-vm [prod|staging|dev|dev2]
      Do \`build-docker\`, \`deploy-docker\` and \`create-vm\` commands.
__EOF__
}

main() {
  local subcmd="$1"
  if [ "${subcmd}" == "help" ]; then
    print_usage
  else
    case "${subcmd}" in
      build-docker)
        build_docker "$2"
        ;;
      deploy)
        deploy_appengine "$2"
        deploy_appengine_legacy "$2"
        deploy_vm "$2"
        ;;
      deploy-docker)
        deploy_docker "$2"
        ;;
      deploy-appengine)
        deploy_appengine "$2"
        ;;
      deploy-appengine-legacy)
        deploy_appengine_legacy "$2"
        ;;
      create-vm)
        create_vm "$2"
        ;;
      deploy-vm)
        deploy_vm "$2"
        ;;
      *)
        die "Unknown sub-command: \"${subcmd}\".  Run \`${0} help\` to print" \
            "the usage."
        ;;
    esac
  fi

  mk_success
}

main "$@"
