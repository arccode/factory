#!/bin/sh
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Starts Goofy in Docker environment.
# This is similar to goofy_control.sh except it's dedicated for Docker sessions.

TOOLKIT_DIR=/usr/local/factory
DATA_DIR=/var/factory
CONFIG_DIR="${DATA_DIR}/config"
RUN_LOCK_DIR=/run/lock

init_dirs() {
  mkdir -p "${DATA_DIR}" "${RUN_LOCK_DIR}" "${CONFIG_DIR}" \
    /var/lib/power_manager
  chmod a+rwxt "${RUN_LOCK_DIR}"
}

init_device_id() {
  # Alternative for /usr/local/factory/init/goofy.d/device_id.sh
  # This ID represents 'docker'.
  echo 'd0c7e2d0c7e2d0c7e2d0c7e2d0c7e2d0' >"${DATA_DIR}/.device_id"
}

disable_plugins() {
  local file="${CONFIG_DIR}/goofy_plugins.json"
  if [ ! -f "${file}" ]; then
    echo '{"plugins": {
      "battery_monitor": {"enabled": false},
      "charge_manager": {"enabled": false},
      "connection_manager": {"enabled": false},
      "core_dump_manager": {"enabled": false},
      "cpu_freq_manager": {"enabled": false},
      "instalog": {"enabled": false}
    }}'>"${file}"
  fi
}

main() {
  set -e
  export "PATH=${TOOLKIT_DIR}/bin:${PATH}"
  init_dirs
  init_device_id
  disable_plugins
  exec "${TOOLKIT_DIR}/bin/goofy" "$@"
}
main "$@"
